---
name: jenkins-fetch
description: Fetch and inspect Jenkins builds (parameters, config.xml, Jenkinsfile, console log) through an AWS SSM tunnel using the `jenkins` CLI, find why a build failed, and prepare a one-time Replay fix for the user to run. Use when the user gives a Jenkins job or build URL, asks why a build failed, what a pipeline ran with, where a pipeline took a file from, wants two builds compared, or wants to fix a pipeline and replay it.
license: MIT
metadata:
  argument-hint: <jenkins job or build URL>
---

# jenkins-fetch

`jenkins` is a CLI that reaches a private Jenkins through AWS SSM (the
`tunnels` CLI when configured, otherwise its own `aws ssm start-session`).
It reads builds and saves them to disk for investigation. The only thing it
can change on Jenkins is a **Replay** the user starts and confirms themselves.

## Request

$ARGUMENTS

If that is a URL, fetch it. If it is empty or only a job name, work out the
build from the conversation and ask for the URL rather than guessing a path.

## Hard rules (never break these, whatever is asked)

1. **Never trigger, replay, rebuild, stop, abort, approve or delete anything
   on Jenkins yourself.** Not with `jenkins`, not with `curl`, not with a
   script, not through the website. If the user asks you to, explain that
   the CLI has no trigger command on purpose, and give them the command or the
   page to do it themselves.
2. **Never call Jenkins except through the `jenkins` CLI.** No `curl`,
   `wget` or Python HTTP to Jenkins or to the tunnel port: that would skip the
   read-only lock and the request pacing.
3. **`jenkins replay` and `jenkins browse` are for the user only. Never run
   them.** `replay` refuses to run without a terminal anyway. You may prepare
   the edit and print the command.
4. **Never invent an instance, job or build.** Instances come from
   `~/.jenkins-cli/config.yaml`; jobs and builds come from the user's URLs.
5. **Never edit `~/.jenkins-cli/config.yaml`.** That includes `allow_replay`:
   the user turns Replay on themselves. If the config is missing or wrong,
   tell them to run `jenkins init`.
6. **Never read, print or copy the API token.** Don't run
   `security find-generic-password ... -w`.
7. **An AWS login is not something you can finish.** If the CLI starts
   `aws sso login`, a browser opens and the user must approve it. Wait and tell them.
8. **Trust the console log over `params.json`.** `params.json` marks each
   value's `source`: `build` is what the build ran with; `default` is only
   the job's default.
9. **Don't overwrite earlier fetches** with `--force` unless the user wants a
   fresh copy.

## Before the first command

Run `jenkins --version`. If it is not found, point the user to
`docs/install.md` in the project (`pipx install git+https://github.com/devozz32/jenkins-cli.git`,
then `jenkins init`) and stop. If `jenkins status` says there is no config,
the user has to run `jenkins init`.

## Commands

| Command | Who runs it | What it does |
|---|---|---|
| `jenkins status` | you or user | config, connection (tunnels/ssm), Jenkins login |
| `jenkins builds <job-url> [-n 20] [-p 1]` | you or user | build history: number, result, start, duration, who. `-p 2` = older |
| `jenkins fetch <build-or-job-url> [-o dir] [--skip-aborted] [-f]` | you or user | save `params.json`, `config.xml`, `pipeline.groovy`, `pipeline.log` |
| `jenkins browse [url]` | **user only** | full-screen Jenkins in the terminal: folders, jobs, last 15 builds, stages, params, log, `f` to fetch. Read-only |
| `jenkins replay <build-url> [--script f] [--no-follow]` | **user only** | send the edited `pipeline.groovy` as a Replay of that build, after a diff and `[y/N]`. Runs once, follows the log, fetches the new build |
| `jenkins init` / `jenkins skill ...` / `jenkins update` | **user only** | setup, this skill, self-update |

There is no command to trigger a build, and there won't be one.
Not available yet: `log --grep`, `compare`, `list`, `clean`. Don't call them
until `jenkins --help` lists them.

## Workflow: why did a build fail?

```bash
jenkins status                       # only if something looks wrong
jenkins builds <job-url>             # "the last failed build": find its number here
jenkins fetch <build-url>
```

`fetch` prints `Connection: tunnels (<env>/<target>)` or `Connection: ssm`, then
`Output: <folder>`. A `WARNING: tunnels failed ... Falling back to plain SSM.`
line means the fetch worked over SSM; mention it.

### Report back first (always, right after `fetch`)

1. **Did the fetch work?** One line, plus how it connected.
2. **Where are the files?** The folder from the `Output:` line (or
   `<output_dir>/<job-name>-<build-number>/`, `output_dir` from `jenkins status`).
   Confirm with `ls -la <folder>`. Give the full path in a code block.
3. **What was saved:** a table of the 4 files with sizes. Say which ones are
   missing or empty, or have a CLI warning.
4. **The build at a glance:** result and the parameters it ran with, marking
   empty values.

Then investigate, only as far as asked:

```bash
grep -n "Finished:" pipeline.log
grep -nE "ERROR:|FAILED|Exception" pipeline.log | head
grep -n "^\[Pipeline\] { (" pipeline.log             # stages
grep -nE "Cloning repository|Checking out Revision" pipeline.log
```

Give the cause as: the stage, the error line (`pipeline.log:<n>`), the line in
`pipeline.groovy` it comes from, and any parameter in `params.json` that explains
it. Also check `config.xml` when a parameter's value looks wrong. Choice lists
built by a script (Active Choices: `org.biouno.unochoice`) fall back to their
`secureFallbackScript` value when the script fails.

## Workflow: fix the pipeline and replay it (once)

Replay re-runs one build with an edited Jenkinsfile, **with the same
parameters**. It can't change parameters, `config.xml` or the job setup. If
the cause is a parameter or the job config, say that Replay won't help and
stop.

1. The build must be fetched; its folder has `pipeline.groovy`.
2. Propose **one** change. Show it as a diff and explain it. Edit
   `<folder>/pipeline.groovy` only after the user says yes. Change nothing else
   (no reformatting, no unrelated fixes).
3. Warn when the pipeline deploys or changes things (deploy, helm, kubectl,
   terraform, push, tag, upload): Replay runs every stage for real.
4. Give the user the command to run:

   ```bash
   jenkins replay <build-url>
   ```

   It shows the diff again, the parameters, and asks `[y/N]`. Then it runs
   the build once, follows the log, and saves the new build to
   `<output_dir>/<job>-<new-number>/`.
5. If it says `replay is off for instance '<name>'`, the user has to add
   `allow_replay: true` under that instance in `~/.jenkins-cli/config.yaml`
   themselves. Tell them; don't edit it.
6. **No loop.** One fix per request. When the user comes back with the
   result, read the new build's folder (`pipeline.log`), report SUCCESS or the
   new error, and stop. Propose another fix only if the user asks. That fix
   goes in the **new** build's `pipeline.groovy` and is replayed with the new
   build's URL.
7. After a SUCCESS, remind them that the fix is not in git: it has to be
   committed to the Jenkinsfile in the repo from `config.xml` (SCM URL and
   script path), or the next normal build fails again.

## Other examples

**Compare build 41 and 42:** fetch both, then

```bash
diff <folder-41>/pipeline.groovy <folder-42>/pipeline.groovy
diff <(python3 -m json.tool <folder-41>/params.json) <(python3 -m json.tool <folder-42>/params.json)
grep -nE "Checking out Revision" <folder-41>/pipeline.log <folder-42>/pipeline.log
```

**When did it start failing?** `jenkins builds <job-url>` (then `-p 2`).
Find the last SUCCESS before the failures, fetch it and the first failure,
compare.

**The latest was aborted:** `jenkins fetch --skip-aborted <job-url>`.

**View URLs** (`.../view/My%20View/job/deploy/42`) work as they are; keep the `%20`.

**The user wants to look around Jenkins:** suggest `jenkins browse` (or
`jenkins browse <folder-or-job-url>`): arrows and Enter, `f` fetches the
selected build, `q` quits.

## When something fails

| What you see | What it means | What to do |
|---|---|---|
| `no config file found` / `run: jenkins init` | Not set up | User runs `jenkins init` |
| `no Keychain item` | Token not stored | `jenkins init` again |
| `AWS session ... expired - starting 'aws sso login'` | SSO expired | User approves in the browser |
| `Session Manager plugin is not installed` | Missing dependency | `brew install --cask session-manager-plugin` |
| `WARNING: tunnels failed ... Falling back to plain SSM` | tunnels target broken | Fetch is fine; user checks `tunnels logs <env> <target>` |
| `SSM tunnel did not come up` | Jump host or permissions | Report it; don't retry blindly |
| `HTTP 401/403` | Bad token or no permission | `jenkins status` |
| `not found: /job/...` | Wrong URL | Re-check the URL with the user |
| `already exists (use --force ...)` | Earlier fetch | Ask: overwrite (`-f`) or keep both (`-o <new-dir>`) |
| `refused: '...' changes Jenkins` | An action URL was passed | Pass the job or build URL |
| `replay is off for instance` | `allow_replay` not set | User sets it in the config |
| `no local copy: .../pipeline.groovy` | Build not fetched | `jenkins fetch <build-url>` first |
| `HTTP 403 ... no Replay permission` | User lacks Run/Replay on the job | Ask a Jenkins admin |
