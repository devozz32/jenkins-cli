# jenkins-cli

Fetch and inspect Jenkins builds on a **private Jenkins** through AWS SSM port
forwarding, from your terminal or from Claude Code.

One command saves everything you need to investigate a build:

```bash
jenkins fetch https://jenkins.example.internal/job/my-job/42/
```

```
~/jenkins-investigations/my-job-42/
├── params.json       # parameters the build ran with (and the job defaults)
├── config.xml        # job definition: repo, branch, script path, triggers
├── pipeline.groovy   # the Jenkinsfile the build actually ran
└── pipeline.log      # full console output
```

**Read-only:** it never triggers builds or changes job configuration.

---

## How it works

```
jenkins CLI ──► 127.0.0.1:<free port> ──► AWS SSM session ──► jump host ──► Jenkins :443
```

1. Reads your settings from `~/.jenkins-cli/config.yaml`.
2. Checks your AWS session and runs `aws sso login` if it has expired.
3. Opens a tunnel: through the [`tunnels`](https://github.com/Zivgl66/tunnels)
   CLI if you've configured it, otherwise its own `aws ssm start-session` on a
   free local port. If `tunnels` is not installed or can't bring its tunnel up,
   it falls back to the plain SSM settings and says so.
4. Calls the Jenkins REST API with your user and API token (from the macOS Keychain).
5. Saves the four files and closes the tunnel.

---

## Install

Requirements: macOS, Python 3.9+, [pipx](https://pipx.pypa.io), AWS CLI v2, the
Session Manager plugin (`brew install --cask session-manager-plugin`), and an
AWS profile allowed to start SSM sessions on the jump host.

```bash
pipx install git+https://github.com/<owner>/jenkins-cli.git
jenkins init                 # interactive setup
jenkins status               # test the connection
jenkins skill install        # optional: the Claude Code skill
```

Step-by-step guide, every `init` prompt explained, and troubleshooting:
**[INSTALL.md](INSTALL.md)**.

---

## Commands

Global options (put them before the command):

| Option | What it does |
|---|---|
| `-i, --instance NAME` | Use this Jenkins instance from the config. Default: the one whose host matches the URL, then `default` |
| `--version` | Print the installed version |
| `-h, --help` | Help for `jenkins` or any command (`jenkins fetch -h`) |

### `jenkins init`

Interactive setup. Creates or extends `~/.jenkins-cli/config.yaml` and stores
the API token in the macOS Keychain.

| Option | What it does |
|---|---|
| `--name NAME` | Name of the instance to create or edit (default: ask). Use a new name to add a second Jenkins |

Run it again any time to change a value.

### `jenkins status`

Checks the config, opens the tunnel, and logs in to Jenkins.

```
Config     : /Users/you/.jenkins-cli/config.yaml
Instance   : main (https://jenkins.example.internal)
Output dir : /Users/you/jenkins-investigations
Connection : tunnels (dev/jenkins)
Local port : 53122
Jenkins    : OK as jdoe
```

### `jenkins fetch <url>`

Saves `params.json`, `config.xml`, `pipeline.groovy` and `pipeline.log` for a build.

| Usage | What it fetches |
|---|---|
| `jenkins fetch <build-url>` | That build (`.../job/my-job/42/`) |
| `jenkins fetch <job-url>` | The latest build of the job (`.../job/my-job/`) |
| `jenkins fetch --skip-aborted <job-url>` | The latest build that was not ABORTED |

| Option | What it does |
|---|---|
| `-o, --output DIR` | Save to this folder instead of `<output_dir>/<job>-<build>/` |
| `--skip-aborted` | With a job URL: skip ABORTED builds |
| `-f, --force` | Overwrite the output folder if it already has files (otherwise you are asked) |

Jobs inside folders work too (`.../job/team/job/my-job/42/`). The output
folder is named after the last job name and the build number.

### `jenkins skill [install | uninstall | status]`

Manages the Claude Code skill (see below).

| Usage | What it does |
|---|---|
| `jenkins skill` | Show whether the skill is installed and where |
| `jenkins skill install` | Copy it to `~/.claude/skills/jenkins-fetch/` |
| `jenkins skill install --link` | Symlink it instead (for editing the skill from a local checkout) |
| `jenkins skill uninstall` | Remove it |

### `jenkins update`

Installs the latest GitHub release with `pipx reinstall` and refreshes the
installed skill.

| Option | What it does |
|---|---|
| `--check` | Only show whether a newer version exists |

---

## Claude Code skill: `/jenkins-fetch`

The package includes a [Claude Code](https://claude.com/claude-code) skill
that teaches Claude how to use this CLI and how to investigate the saved files.

```bash
jenkins skill install     # then restart Claude Code
```

Use it in Claude Code:

```
/jenkins-fetch https://jenkins.example.internal/job/my-job/42/
```

Or just paste a build URL and ask, for example:

- "Why did this build fail?"
- "Which branch and parameters did it run with?"
- "Where did the pipeline take this template file from?"
- "Compare build 41 and 42."

What the skill makes Claude do (and not do):

- Fetch the build with `jenkins fetch`, then work from the files with `grep`
  instead of reading whole logs.
- Trust the console log over the parameter defaults for what actually happened.
- Never guess job or build names, never edit your config, and never read your API token.
- If AWS SSO opens a browser login, wait for you to approve it.
- Map each known error message to its fix.

The skill lives in [`jenkins_cli/skills/jenkins-fetch/SKILL.md`](jenkins_cli/skills/jenkins-fetch/SKILL.md).

---

## Config

`~/.jenkins-cli/config.yaml`, written by `jenkins init` (set
`JENKINS_CLI_CONFIG` to use a different path). Full example:
[`jenkins_cli/config.example.yaml`](jenkins_cli/config.example.yaml).

```yaml
default: main
output_dir: ~/jenkins-investigations

instances:
  main:
    url: https://jenkins.example.internal
    user: your-jenkins-user
    token: keychain:jenkins-main       # or env:VAR_NAME
    tunnel:
      # tunnels_target: <env>/<target>  # used when the tunnels CLI is installed
      ssm:
        profile: <aws-profile>
        region: <aws-region>
        instance: <ssm-instance-id>
        local_port: auto
```

| Key | Required | Meaning |
|---|---|---|
| `default` | no | Instance used when the URL doesn't match one (default: the first) |
| `output_dir` | no | Where builds are saved (default: `~/jenkins-investigations`) |
| `instances.<name>.url` | yes | Jenkins base URL |
| `instances.<name>.user` | yes | Your Jenkins username |
| `instances.<name>.token` | yes | `keychain:<item>` or `env:<VAR>`. The token itself is never in the file |
| `tunnel.tunnels_target` | one of these | `<env>/<target>` in the `tunnels` CLI |
| `tunnel.ssm.profile` / `region` / `instance` | one of these | AWS profile, region and jump host for the plain SSM tunnel |
| `tunnel.ssm.remote_host` | no | Host the jump host forwards to (default: host from `url`) |
| `tunnel.ssm.remote_port` | no | Default `443` |
| `tunnel.ssm.local_port` | no | `auto` (a free port) or a fixed number |

You can list several instances; `fetch` picks the right one from the URL's host.

---

## Multiple Jenkins servers

One config can hold several Jenkins servers, for example a dev and a prod one,
each with its own URL, user, token, AWS account and jump host.

Add one with `init` and a new name. Existing instances are kept:

```bash
jenkins init --name prd
```

```yaml
default: dev
instances:
  dev:
    url: https://jenkins-dev.example.internal
    user: your-user
    token: keychain:jenkins-dev            # each instance has its own token
    tunnel:
      tunnels_target: dev-account/jenkins
      ssm: { profile: <dev-profile>, region: <region>, instance: <dev-jump-host-id> }
  prd:
    url: https://jenkins-prd.example.internal
    user: your-user
    token: keychain:jenkins-prd
    tunnel:
      tunnels_target: prd-account/jenkins
      ssm: { profile: <prd-profile>, region: <region>, instance: <prd-jump-host-id> }
```

Which instance a command uses:

1. `-i <name>` if given: `jenkins -i prd status`
2. Otherwise the one whose `url` host matches the URL you pass to `fetch`.
   Paste a prod build URL and it uses the prod account, tunnel and token.
3. Otherwise `default`. This is what `jenkins status` uses, since it has no URL.

```bash
jenkins fetch https://jenkins-dev.example.internal/job/my-job/42/   # -> dev
jenkins fetch https://jenkins-prd.example.internal/job/my-job/42/   # -> prd
jenkins -i prd status
```

With the `tunnels` CLI, add a `jenkins` target in each account's block
(`dev-account`, `prd-account`) and point each instance's `tunnels_target` at it.

All instances share one `output_dir`. A dev and a prod job with the same name
and build number land in the same folder; you are asked before anything is
overwritten. Use `-o` to keep them apart.

---

## Uninstall

```bash
jenkins skill uninstall
pipx uninstall jenkins-cli
rm -rf ~/.jenkins-cli
```

Then delete the token from the Keychain (one per instance; see [INSTALL.md](INSTALL.md#9-update-and-uninstall)).

---

## License

MIT
