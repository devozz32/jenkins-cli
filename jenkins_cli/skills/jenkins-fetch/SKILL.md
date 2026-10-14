---
name: jenkins-fetch
description: Fetch and inspect Jenkins builds (parameters, config.xml, Jenkinsfile, console log) through an AWS SSM tunnel using the `jenkins` CLI. Use when the user gives a Jenkins job or build URL, asks why a build failed, what a pipeline ran with, where a pipeline took a file from, or wants two builds compared.
license: MIT
metadata:
  argument-hint: <jenkins job or build URL>
---

# jenkins-fetch

`jenkins` is a read-only CLI that reaches a private Jenkins through AWS SSM
(the `tunnels` CLI when configured, otherwise its own `aws ssm start-session`)
and saves build data to disk for investigation.

## Request

$ARGUMENTS

If that is a URL, fetch it. If it is empty, work out the build from the
conversation and ask for the URL rather than guessing a job name.

## Before the first command

Run `jenkins --version`. If the command is not found, the CLI is not
installed: point the user to the install steps in the project README
(`pipx install git+https://github.com/<owner>/jenkins-cli.git`, then
`jenkins init`) and stop. If `jenkins status` says there is no config, the
user has to run `jenkins init` themselves.

## Rules that prevent the common failures

1. **Never invent an instance, job or build.** Instances come from
   `~/.jenkins-cli/config.yaml`; jobs and builds come from the user's URLs.
2. **Never hardcode a port, host, profile or instance ID.** The CLI reads
   them from the config and picks a free port itself.
3. **Never edit `~/.jenkins-cli/config.yaml` yourself.** If it is missing or
   wrong, tell the user to run `jenkins init` (it is interactive and stores the
   token in the Keychain).
4. **Never read, print or copy the API token.** Do not run
   `security find-generic-password ... -w`.
5. **An AWS login is not something you can finish.** If the CLI starts
   `aws sso login`, a browser opens and the user must approve it. Wait and tell them.
6. **Trust the console log over `params.json` for what actually happened.**
   `params.json` marks each value's `source`: `build` is what the build ran
   with; `default` is only the job's default.
7. **The output folder may already have older fetches.** Don't overwrite with
   `--force` unless the user wants a fresh copy.

## Workflow

```bash
jenkins status                       # config, connection method, tunnel, Jenkins login
jenkins fetch <build-url>            # one build
jenkins fetch <job-url>              # latest build of the job
jenkins fetch --skip-aborted <job-url>
jenkins fetch <url> -o <dir>         # custom output folder
jenkins -i <instance> fetch <url>    # pick an instance explicitly
jenkins builds <job-url>             # history: which builds failed, when, who started them
```

`fetch` prints `Connection: tunnels (<env>/<target>)` or `Connection: ssm`, then the
output folder. A `WARNING: tunnels failed ... Falling back to plain SSM.` line means
the tunnels target is broken but the fetch still worked over SSM; mention it in the
report. The folder contains:

| File | What it holds |
|---|---|
| `params.json` | parameters with type, default, choices, `value` and `source` (`build`/`default`) |
| `config.xml` | job definition: SCM repo/branch/script path, triggers |
| `pipeline.groovy` | the Jenkinsfile the build ran (from the replay page) |
| `pipeline.log` | full console output |

## Report back to the user (always, right after `fetch`)

Before any investigation, tell the user plainly what happened. Use this order:

1. **Did the fetch work?** One line: "The fetch worked" or "The fetch failed",
   and how it connected (`tunnels` or SSM, from the CLI output).
2. **Where are the files?** Check it, don't assume it:
   - Take the folder from the `Output:` line the CLI printed.
   - If that line is missing (the fetch stopped early) or unclear, look up the
     configured folder: `jenkins status` prints `Output dir`, or read
     `output_dir` in `~/.jenkins-cli/config.yaml` (read only, never edit it).
     The build folder is `<output_dir>/<job-name>-<build-number>/` unless `-o` was used.
   - Run `ls -la <folder>` to confirm the folder and files really exist.
   - Give the full path in a code block, plus `open <folder>` to open it in Finder.
3. **What was saved:** a table with each of the 4 files, its size
   (`ls -la <folder>`), and one line on what it holds. If a file is missing or
   empty, or the CLI printed a warning for it (no permission for config.xml,
   no Jenkinsfile on the replay page), say so in that row.
4. **The build at a glance:** its result (SUCCESS / FAILURE / ABORTED /
   IN_PROGRESS) and the parameters it ran with, marking empty values.

Only then investigate, and only as far as the user asked. If they only asked
to fetch, stop after the report and offer to look at why it failed.

If the fetch itself failed, say so first, quote the error line, and give the
fix from the table under "When something fails".

## Investigating a build

After `fetch`, work from the files with grep rather than reading whole logs:

```bash
grep -n "Finished:" pipeline.log                     # result
grep -nE "ERROR|FAILED|Exception" pipeline.log | head
grep -nE "Cloning repository|Checking out Revision" pipeline.log   # repos, branches, commits
grep -n "^\[Pipeline\] { (" pipeline.log             # stage starts
```

To compare two builds, fetch both, then diff `pipeline.groovy`, the
checked-out repos/branches, and the relevant log lines side by side.

## Examples

**"Fetch this: https://jenkins.example.internal/job/team/job/deploy/42/"**

```bash
jenkins fetch https://jenkins.example.internal/job/team/job/deploy/42/
ls -la ~/jenkins-investigations/deploy-42/      # path from the Output: line
```

Then the report: "The fetch worked, connected through tunnels. Files are in
`~/jenkins-investigations/deploy-42/`" + the file table + result and parameters.
Stop there and offer to look into the result.

**"Why did the latest build of deploy fail?"** (job URL, no build number)

```bash
jenkins fetch https://jenkins.example.internal/job/team/job/deploy/
cd <output folder>
grep -n "Finished:" pipeline.log
grep -nE "ERROR|FAILED|Exception" pipeline.log | head
grep -n "^\[Pipeline\] { (" pipeline.log       # which stage it was in
```

Report first, then the cause: the error line, the stage, and the line in
`pipeline.groovy` it points to. Check `params.json` for empty or default values
that explain it.

**URLs copied from a view** (`.../view/My%20View/job/deploy/42`) work as they
are. Pass them unchanged, with the `%20`; don't rewrite them.

**"The latest one was aborted, get the one before"**

```bash
jenkins fetch --skip-aborted https://jenkins.example.internal/job/team/job/deploy/
```

**"Compare build 41 and 42"**

```bash
jenkins fetch https://jenkins.example.internal/job/team/job/deploy/41/
jenkins fetch https://jenkins.example.internal/job/team/job/deploy/42/
diff ~/jenkins-investigations/deploy-41/pipeline.groovy ~/jenkins-investigations/deploy-42/pipeline.groovy
diff <(python3 -m json.tool ~/jenkins-investigations/deploy-41/params.json) \
     <(python3 -m json.tool ~/jenkins-investigations/deploy-42/params.json)
grep -nE "Checking out Revision" ~/jenkins-investigations/deploy-4{1,2}/pipeline.log
```

**"When did this job start failing?"**

```bash
jenkins builds https://jenkins.example.internal/job/team/job/deploy/        # newest 20
jenkins builds https://jenkins.example.internal/job/team/job/deploy/ -p 2   # the 20 before
```

Find the last SUCCESS before the failures, then fetch that build and the first
failed one and compare them. Page instead of raising `-n` above what you need.

**"Fetch 42 again"** (folder already exists)

The CLI stops with `already exists (use --force to overwrite)`. Ask the user:
overwrite (`-f`), or keep both (`-o ~/jenkins-investigations/deploy-42-new`).

**"Is Jenkins reachable?"**

```bash
jenkins status
```

Expect `Jenkins : OK as <user>`. Anything else: use the table below.

## When something fails

| What you see | What it means | What to do |
|---|---|---|
| `no config file found` / `run: jenkins init` | Not set up | Ask the user to run `jenkins init` |
| `no Keychain item` | Token not stored | `jenkins init` again |
| `AWS session ... expired - starting 'aws sso login'` | SSO expired | Tell the user to approve in the browser |
| `Session Manager plugin is not installed` | Missing dependency | `brew install --cask session-manager-plugin` |
| `WARNING: tunnels failed ... Falling back to plain SSM` | tunnels target broken, SSM used | Fetch is fine; tell the user to check `tunnels logs <env> <target>` |
| `SSM tunnel did not come up` | Jump host or permissions | Report the message; don't retry blindly |
| `HTTP 401/403` | Bad token or no permission | Check user/token with `jenkins status` |
| `not found: /job/...` | Wrong URL | Re-check the URL with the user |
| `already exists (use --force ...)` | Folder from an earlier fetch | Ask before overwriting |

## Commands

| Command | What it does |
|---|---|
| `jenkins status` | Check config, tunnel and Jenkins login |
| `jenkins fetch <url> [-o dir] [--skip-aborted] [-f]` | Save the 4 files for a build |
| `jenkins builds <job-url> [-n 20] [-p 1]` | Build history: number, result, start, duration, who. `-p 2` = older |
| `jenkins browse [url]` | Interactive Jenkins UI for the **user** (folders, jobs, last 15 builds, stages, log). Never run it yourself |
| `jenkins init [--name N]` | Interactive setup (user runs it, not Claude) |
| `jenkins --version` / `jenkins update [--check]` | Version / self-update from GitHub |
| `jenkins skill [install\|uninstall]` | Install or remove this skill (user runs it) |

`jenkins browse` is an interactive full-screen UI for people. **Do not run it**
(it waits for keys); use `builds` and `fetch`. Suggest it to the user when they
want to look around Jenkins themselves.

Planned, **not available yet**: `log --grep`, `compare`, `list`, `clean`.
Do not call them until `jenkins --help` lists them.
