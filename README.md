# jenkins-cli

<p align="center">
  <a href="#install">install</a> ·
  <a href="#quick-start">quick start</a> ·
  <a href="#commands">commands</a> ·
  <a href="docs/install.md">step-by-step install</a> ·
  <a href="docs/install.md#already-use-tunnels-the-short-path">already use tunnels?</a> ·
  <a href="docs/configuration.md">configuration</a> ·
  <a href="docs/how-it-works.md">how it works</a> ·
  <a href="docs/troubleshooting.md">troubleshooting</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-666666?labelColor=333333" alt="MIT license" /></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-666666?labelColor=333333" alt="Python 3.9+" />
  <img src="https://img.shields.io/badge/platform-macOS-666666?labelColor=333333" alt="macOS" />
  <img src="https://img.shields.io/badge/jenkins-read--only-666666?labelColor=333333" alt="read-only" />
  <a href="https://github.com/devozz32/jenkins-cli/releases"><img src="https://img.shields.io/github/v/release/devozz32/jenkins-cli?labelColor=333333&color=666666" alt="latest release" /></a>
</p>

---

**Look at and fetch builds on a private Jenkins through an AWS SSM tunnel,
from your terminal or from an AI agent.**

- **one command per build.** `jenkins fetch <url>` saves the parameters, the
  job config, the Jenkinsfile the build really ran, and the full log.
- **Jenkins in the terminal.** `jenkins browse` walks folders, jobs and builds
  with the arrow keys, and shows stages, parameters, the log and the
  Jenkinsfile. No browser, no copying URLs.
- **read-only, enforced.** The client sends only GET requests and refuses any
  URL that names a Jenkins action (`build`, `stop`, `doDelete`, `replay/run`,
  ...). Nothing is triggered, replayed or deleted.
- **gentle on the server.** One small request per screen, cached, about 5
  requests per second at most, and never a background poll.
- **works with or without [`tunnels`](https://github.com/Zivgl66/tunnels).**
  If you use it, the CLI reuses its tunnel. If not, or if it fails, the CLI
  opens its own `aws ssm start-session` on a free port and closes it after.
- **no secrets on disk.** The API token lives in the macOS Keychain; the config
  file only holds a reference to it.
- **several Jenkins servers.** Dev, staging, prod: each with its own account,
  jump host and token. A pasted URL picks the right one.
- **agents can drive it.** A bundled skill teaches Claude Code to fetch a build
  and investigate it from the files. [how to install it](docs/agent-skill.md)
- **small.** Plain Python, `pyyaml` is the only dependency.

```console
$ jenkins fetch https://jenkins.example.internal/job/team/job/deploy/42/
Connection: tunnels (dev/jenkins), port 53122

Build:  https://jenkins.example.internal/job/team/job/deploy/42
Output: /Users/you/jenkins-investigations/deploy-42/
...
  Result: FAILURE
  Parameters (2):
    BRANCH: main [StringParameterDefinition] (build)
    ENV: dev [ChoiceParameterDefinition] (build)
...
Done. All files in /Users/you/jenkins-investigations/deploy-42/
```

```
~/jenkins-investigations/deploy-42/
├── params.json       # parameters the build ran with, and the job defaults
├── config.xml        # job definition: repo, branch, script path, triggers
├── pipeline.groovy   # the Jenkinsfile the build actually ran
└── pipeline.log      # full console output
```

## Requirements

macOS, plus:

| Tool | Install |
| --- | --- |
| `aws` CLI v2, with a profile allowed to start SSM sessions | `brew install awscli` |
| `session-manager-plugin` | `brew install --cask session-manager-plugin` |
| `pipx` | `brew install pipx && pipx ensurepath` |
| [`tunnels`](https://github.com/Zivgl66/tunnels) *(optional)* | `pipx install git+https://github.com/Zivgl66/tunnels.git` |

Python 3.9 or newer. You also need a Jenkins API token (Jenkins → your user →
**Configure** → **API Token**), and a jump host with a running SSM agent that
can reach Jenkins on port 443.

## Install

```bash
pipx install git+https://github.com/devozz32/jenkins-cli.git && jenkins init
```

`jenkins init` asks for the Jenkins URL, your user, the API token (stored in
the Keychain) and how to reach Jenkins, then writes
`~/.jenkins-cli/config.yaml`. Run it again to change a value, or
`jenkins init --name prd` to add another Jenkins.

`jenkins --version` prints the installed version. `jenkins update` installs the
latest GitHub release and refreshes the agent skill.

Every prompt explained, AWS SSO, and setting up `tunnels`:
**[docs/install.md](docs/install.md)**.
Already use `tunnels`? Add one `jenkins` target and answer `init` with it:
**[the short path](docs/install.md#already-use-tunnels-the-short-path)**.

## Quick start

```bash
jenkins status                                                   # config, tunnel, Jenkins login
jenkins browse                                                   # look around
jenkins builds https://jenkins.example.internal/job/deploy/      # last 20 builds
jenkins fetch  https://jenkins.example.internal/job/deploy/42/   # save build 42
```

`status` should end with `Jenkins : OK as <you>`. If it doesn't, see
[troubleshooting](docs/troubleshooting.md).

## Commands

| Command | What it does |
| --- | --- |
| `jenkins browse [url]` | Jenkins in the terminal: folders → jobs → last 15 builds → stages, parameters, log, Jenkinsfile. Starts at the top, or at the folder, job or build in `url`. [Keys below](#keys-in-browse) |
| `jenkins builds <job-url>` | A job's builds, newest first: number, result, start, duration, who started it. `-n` builds per page (max 100, default 20), `-p 2` the next page back |
| `jenkins fetch <url>` | Save `params.json`, `config.xml`, `pipeline.groovy`, `pipeline.log` for a build URL, or for the latest build of a job URL |
| `jenkins fetch <job-url> --skip-aborted` | The latest build that was not ABORTED |
| `jenkins fetch <url> -o <dir>` | Save somewhere else than `<output_dir>/<job>-<build>/` |
| `jenkins fetch <url> -f` | Overwrite a folder from an earlier fetch (otherwise you are asked) |
| `jenkins status` | Check the config, open the tunnel, log in to Jenkins, and show which way it connected |
| `jenkins init [--name N]` | Create or extend the config; stores the token in the Keychain |
| `jenkins -i <name> <command>` | Use that Jenkins from the config instead of the one matched by the URL |
| `jenkins skill [install\|uninstall]` | Install the agent skill into `~/.claude/skills/` (`--link` to symlink it). No argument: show where it is |
| `jenkins update` | Install the latest GitHub release; asks first (`-y` skips the question). `--check` only looks |
| `jenkins --version` | Print the installed version |

Job URLs copied from a view (`.../view/My%20View/job/deploy/42/`) and jobs in
folders (`.../job/team/job/deploy/`) work as they are.

`jenkins` on its own, `jenkins --help`, `status` and `init` show the logo when a
terminal is attached. Piped output never has it, and `NO_COLOR=1` turns colour
off.

### Keys in browse

| Key | What it does |
| --- | --- |
| `↑` `↓` `PgUp` `PgDn` `g` `G` | Move, page, top, end |
| `Enter` / `→` | Open the folder, job or build |
| `←` / `Backspace` | Back |
| `/` | Filter a list, or search a log (`n` / `N` next, previous) |
| `l` `j` `f` | On a build: log (opens at the end), Jenkinsfile, save the 4 files like `fetch` |
| `r` | Reload this screen from Jenkins |
| `q` | Quit. Prints how many requests were sent |

## Docs

- [install, step by step](docs/install.md): every `init` prompt, AWS SSO,
  setting up `tunnels`, update and uninstall
- [configuration](docs/configuration.md): the config file, every key, several
  Jenkins servers, the `tunnels` target
- [how it works](docs/how-it-works.md): the two ways to connect and the
  fallback, the read-only lock, what each command asks Jenkins for
- [agent skill](docs/agent-skill.md): let Claude Code fetch and investigate
  builds for you
- [troubleshooting](docs/troubleshooting.md): every error message, and the
  known limits
- [backlog](docs/BACKLOG.md): what is not built yet
- [changelog](CHANGELOG.md)

## Develop

```bash
git clone https://github.com/devozz32/jenkins-cli.git && cd jenkins-cli
pipx install --editable .     # your edits take effect with no reinstall
python3 -m py_compile jenkins_cli/*.py
jenkins status
```

Keep the repo free of company values: no hostnames, account numbers, instance
IDs, profile or job names. Use `jenkins.example.internal` and
`<ssm-instance-id>`. Never add a request that is not a GET, and keep the
read-only lock in `jenkins_cli/api.py`.

## Releasing

Bump `version` in `pyproject.toml`, add the release to
[CHANGELOG.md](CHANGELOG.md), then:

```bash
git push && git tag vX.Y.Z && git push --tags
gh release create vX.Y.Z --generate-notes
```

`jenkins update` on every machine picks the new release up from there.

## License

MIT. See [LICENSE](LICENSE).
