"""jenkins - fetch and inspect Jenkins builds through AWS SSM port forwarding."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

from . import __version__, awslogin, banner, browse, builds, config, connect, fetch, secrets, skill, update
from .api import Jenkins, JenkinsError


def log(msg: str = "") -> None:
    print(msg, flush=True)


def err(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or (default or "")


def _describe(inst: dict, how: str) -> str:
    return f"tunnels ({inst['tunnel']['tunnels_target']})" if how == "tunnels" else "ssm"


def _client(inst: dict, port: int) -> Jenkins:
    return Jenkins(port, inst["user"], secrets.resolve(inst["token"]))


# ─── init ───────────────────────────────────────────────────────────────────

def _online_ssm_instances(profile: str, region: str) -> list[tuple[str, str]]:
    out = subprocess.run(
        ["aws", "ssm", "describe-instance-information", "--profile", profile, "--region", region,
         "--query", "InstanceInformationList[?PingStatus=='Online'].[InstanceId,ComputerName]",
         "--output", "text"],
        capture_output=True, text=True,
    )
    rows = []
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if parts and parts[0].startswith("i-"):
            rows.append((parts[0], parts[1] if len(parts) > 1 else ""))
    return rows


def cmd_init(args) -> int:
    banner.show()
    data = config.load_or_empty()
    name = args.name or _ask("Name for this Jenkins instance", "main")
    existing = data["instances"].get(name, {})
    ex_ssm = (existing.get("tunnel") or {}).get("ssm") or {}

    url = _ask("Jenkins URL", existing.get("url")).rstrip("/")
    user = _ask("Jenkins user", existing.get("user"))

    token_ref = f"keychain:jenkins-{name}"
    if existing.get("token") and _ask("Replace the stored API token? (y/N)", "n").lower() != "y":
        token_ref = existing["token"]
    else:
        secrets.store_keychain(f"jenkins-{name}")

    tunnel: dict = {}
    if shutil.which("tunnels"):
        current = (existing.get("tunnel") or {}).get("tunnels_target", "")
        target = _ask("tunnels target as <env>/<target> (empty = don't use tunnels)", current)
        if target:
            tunnel["tunnels_target"] = target

    if _ask("Configure plain AWS SSM fallback? (Y/n)", "y").lower() != "n":
        profiles = awslogin.profiles()
        if profiles:
            log("AWS profiles: " + ", ".join(profiles))
        profile = _ask("AWS profile", ex_ssm.get("profile"))
        region = _ask("AWS region", ex_ssm.get("region") or "eu-west-1")
        awslogin.ensure_login(profile)
        found = _online_ssm_instances(profile, region)
        if found:
            log("Online SSM instances:")
            for iid, host in found:
                log(f"  {iid}  {host}")
        instance = _ask("SSM instance (jump host)", ex_ssm.get("instance") or (found[0][0] if len(found) == 1 else None))
        tunnel["ssm"] = {"profile": profile, "region": region, "instance": instance, "local_port": "auto"}

    data["instances"][name] = {"url": url, "user": user, "token": token_ref, "tunnel": tunnel}
    data.setdefault("default", name)
    data["output_dir"] = _ask("Output folder for fetched builds",
                              data.get("output_dir") or config.DEFAULT_OUTPUT_DIR)
    config.validate_instance(name, data["instances"][name])
    config.save(data)
    log(f"Saved {config.CONFIG_PATH}. Test it with: jenkins status")
    return 0


# ─── status ─────────────────────────────────────────────────────────────────

def cmd_status(args) -> int:
    banner.show()
    data = config.load()
    name, inst = config.instance(data, args.instance)
    config.validate_instance(name, inst)
    log(f"Config     : {config.CONFIG_PATH}")
    log(f"Instance   : {name} ({inst['url']})")
    log(f"Output dir : {config.output_dir(data)}")
    with connect.open_port(inst) as (port, how):
        log(f"Connection : {_describe(inst, how)}")
        log(f"Local port : {port}")
        me = _client(inst, port).whoami()
        ok = me.get("authenticated") and me.get("name") not in (None, "anonymous")
        log(f"Jenkins    : {'OK' if ok else 'NOT AUTHENTICATED'} as {me.get('name')}")
        return 0 if ok else 1


# ─── builds ─────────────────────────────────────────────────────────────────

def cmd_builds(args) -> int:
    data = config.load()
    name, inst = config.instance(data, args.instance, args.url)
    config.validate_instance(name, inst)
    job, _ = fetch.split_url(Jenkins.path_of(args.url))
    size = max(1, min(args.limit, 100))

    with connect.open_port(inst) as (port, how):
        log(f"Connection: {_describe(inst, how)}, port {port}")
        args.page = max(1, args.page)
        d = builds.page(_client(inst, port), job, args.page, size)

    first = (d.get("firstBuild") or {}).get("number")
    last = (d.get("lastBuild") or {}).get("number")
    rows = d["allBuilds"]
    log(f"Job   : {job}")
    log(f"Builds: #{first} .. #{last}" if last else "Builds: none")
    if not rows:
        log(f"No builds on page {args.page}.")
        return 0
    log("")
    for line in builds.table(rows, color=banner._color_ok(sys.stdout)):
        log(line)
    log("")
    log(f"Page {args.page} ({len(rows)} builds)." + (
        f" Older: jenkins builds {args.url} -p {args.page + 1}" + (f" -n {size}" if size != 20 else "")
        if len(rows) == size and rows[-1]["number"] != first else " This is the oldest page."))
    return 0


# ─── browse ─────────────────────────────────────────────────────────────────

def cmd_browse(args) -> int:
    data = config.load()
    chosen = args.instance
    if not chosen and not args.url and len(data["instances"]) > 1:
        names = list(data["instances"])
        for i, n in enumerate(names, 1):
            log(f"  {i}. {n}  ({data['instances'][n].get('url')})")
        pick = _ask("Which Jenkins? (number)", "1")
        chosen = names[int(pick) - 1] if pick.isdigit() and 0 < int(pick) <= len(names) else pick
    name, inst = config.instance(data, chosen, args.url)
    config.validate_instance(name, inst)
    if not sys.stdout.isatty():
        err("browse needs an interactive terminal (use builds / fetch in scripts)")
        return 1
    start = Jenkins.path_of(args.url) if args.url else "/"
    with connect.open_port(inst) as (port, how):
        jk = _client(inst, port)
        header = f"jenkins-cli  │  {name}  {inst['url']}  │  {_describe(inst, how)}  │  read-only"
        try:
            browse.run(jk, inst["url"], header, config.output_dir(data), start, unquote(start) or "/")
        except KeyboardInterrupt:
            pass
    log(f"Closed. {jk.requests} GET requests sent, nothing changed on Jenkins.")
    return 0


# ─── fetch ──────────────────────────────────────────────────────────────────

def cmd_fetch(args) -> int:
    data = config.load()
    name, inst = config.instance(data, args.instance, args.url)
    config.validate_instance(name, inst)
    job, number = fetch.split_url(Jenkins.path_of(args.url))

    with connect.open_port(inst) as (port, how):
        log(f"Connection: {_describe(inst, how)}, port {port}")
        jk = _client(inst, port)
        if number is None:
            if args.skip_aborted:
                log("Searching for latest non-aborted build...")
                number, result = fetch.latest_not_aborted(jk, job, log=log)
            else:
                log("Resolving latest build...")
                number, result = fetch.latest(jk, job)
            log(f"Found: #{number} ({result})")

        out = Path(args.output).expanduser() if args.output else config.output_dir(data) / fetch.dir_name(job, number)
        if out.exists() and any(out.iterdir()) and not args.force:
            if not sys.stdin.isatty() or _ask(f"{out} already exists. Overwrite? (y/N)", "n").lower() != "y":
                err(f"{out} already exists (use --force to overwrite)")
                return 1
        out.mkdir(parents=True, exist_ok=True)

        fetch.save_build(jk, inst["url"], job, number, out, log=log)
    return 0


# ─── skill ──────────────────────────────────────────────────────────────────

def cmd_skill(args) -> int:
    if args.action == "install":
        log(skill.install(link=args.link))
        log(f"Restart Claude Code, then use: /{skill.NAME} <build-url>")
    elif args.action == "uninstall":
        log(f"Removed {skill.TARGET}" if skill.remove() else f"Not installed: {skill.TARGET}")
    else:
        state = "symlink" if skill.TARGET.is_symlink() else "installed" if skill.installed() else "not installed"
        log(f"Skill  : {skill.NAME} ({state})")
        log(f"Path   : {skill.TARGET}")
        log(f"Source : {skill.SOURCE}")
    return 0


# ─── update ─────────────────────────────────────────────────────────────────

def cmd_update(args) -> int:
    return update.run(check_only=args.check, yes=args.yes)


# ─── main ───────────────────────────────────────────────────────────────────

class _Parser(argparse.ArgumentParser):
    """Top-level parser: `jenkins --help` starts with the logo."""

    def print_help(self, file=None):
        banner.show(file)
        super().print_help(file)


EXAMPLES = """\
examples:
  jenkins init                                   first-time setup (asks for URL, user, token, tunnel)
  jenkins status                                 check config, tunnel and Jenkins login
  jenkins fetch https://jenkins.example.internal/job/my-job/42/
                                                 save params, config.xml, Jenkinsfile and log of build 42
  jenkins fetch https://jenkins.example.internal/job/my-job/
                                                 same for the latest build
  jenkins fetch --skip-aborted <job-url>         latest build that was not ABORTED
  jenkins fetch <build-url> -o ~/my-folder       save somewhere else
  jenkins browse                                 Jenkins in the terminal: arrows + Enter, q to quit
  jenkins browse <folder-or-job-url>             start inside a folder or job
  jenkins builds <job-url>                       last 20 builds: result, time, duration, who
  jenkins builds <job-url> -p 2 -n 50            older builds, 50 per page
  jenkins -i prd status                          use the instance named 'prd' from the config

Claude Code skill (/jenkins-fetch):
  jenkins skill install                          add the skill to ~/.claude/skills, then restart Claude Code
  jenkins skill                                  is it installed, and where

  then in Claude Code:
    /jenkins-fetch https://jenkins.example.internal/job/my-job/42/
    "why did https://jenkins.example.internal/job/my-job/42/ fail?"
    "what parameters and branch did build 42 run with?"
    "compare build 41 and 42 of my-job"

  Claude runs the same jenkins commands, reports where the files are, then investigates.
"""


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="jenkins", description=__doc__, epilog=EXAMPLES,
                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"jenkins-cli {__version__}")
    p.add_argument("-i", "--instance", help="instance name from the config (default: by URL host, then 'default')")
    sub = p.add_subparsers(dest="command", metavar="<command>", parser_class=argparse.ArgumentParser)

    s = sub.add_parser("init", help="create or extend ~/.jenkins-cli/config.yaml")
    s.add_argument("--name", help="instance name (default: ask)")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("status", help="check config, tunnel and Jenkins login")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("browse", help="Jenkins in the terminal: folders, jobs, builds, stages, log (read-only)")
    s.add_argument("url", nargs="?", help="start here: a folder, job or build URL (default: the top)")
    s.set_defaults(func=cmd_browse)

    s = sub.add_parser("builds", help="list a job's builds: result, start time, duration, who started it")
    s.add_argument("url", help="job URL (a build URL also works)")
    s.add_argument("-n", "--limit", type=int, default=20, help="builds per page, max 100 (default: 20)")
    s.add_argument("-p", "--page", type=int, default=1, help="page number, 1 = newest (default: 1)")
    s.set_defaults(func=cmd_builds)

    s = sub.add_parser("fetch", help="save config.xml, params.json, pipeline.groovy, pipeline.log for a build")
    s.add_argument("url", help="job URL (latest build) or build URL")
    s.add_argument("-o", "--output", help="output folder (default: <output_dir>/<job>-<build>)")
    s.add_argument("--skip-aborted", action="store_true", help="with a job URL: skip ABORTED builds")
    s.add_argument("-f", "--force", action="store_true", help="overwrite an existing output folder")
    s.set_defaults(func=cmd_fetch)

    s = sub.add_parser("skill", help="install the Claude Code skill (/jenkins-fetch) into ~/.claude/skills")
    s.add_argument("action", nargs="?", choices=["install", "uninstall", "status"], default="status")
    s.add_argument("--link", action="store_true", help="symlink instead of copy (for editing the skill)")
    s.set_defaults(func=cmd_skill)

    s = sub.add_parser("update", help="install the latest release from GitHub")
    s.add_argument("--check", action="store_true", help="only show whether an update exists")
    s.add_argument("-y", "--yes", action="store_true", help="install without asking")
    s.set_defaults(func=cmd_update)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args) or 0
    except (config.ConfigError, secrets.SecretError, connect.ConnectError,
            awslogin.AwsError, JenkinsError, update.UpdateError) as exc:
        err(str(exc))
        return 1
    except KeyboardInterrupt:
        err("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
