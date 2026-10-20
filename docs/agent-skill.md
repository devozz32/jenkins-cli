# Using jenkins-cli from an AI agent

`jenkins_cli/skills/jenkins-fetch/SKILL.md` teaches a coding agent to fetch a
build and investigate it from the saved files, instead of guessing at job
names, ports or tokens.

It is a plain markdown file in the [Agent Skills](https://agentskills.io)
format, and it ships inside the package, so there is nothing to download
separately.

## Install it

**Claude Code**, for every project:

```bash
jenkins skill install
```

This copies the skill to `~/.claude/skills/jenkins-fetch/`. `jenkins update`
refreshes it with each new version, and `jenkins skill` shows where it is.

Restart the session afterwards. Skills load at start-up, so one added
mid-session is not picked up.

**Other clients** read skills from their own directory. Copy the same file
there:

```bash
cp -R "$(jenkins skill | sed -n 's/^Source *: //p')" <client-skills-dir>/
```

Working on the skill itself? `jenkins skill install --link` symlinks it to your
checkout, so edits take effect on the next session.

## Use it

Ask for what you want, not for the commands:

```
why did https://jenkins.example.internal/job/team/job/deploy/42/ fail?
```

The agent runs `jenkins fetch`, tells you whether it worked and where the files
are, then reads the log with `grep` and points at the failing stage and the
line in the Jenkinsfile. In Claude Code you can also call it directly:

```
/jenkins-fetch https://jenkins.example.internal/job/team/job/deploy/42/
```

Other things to ask:

```
what parameters and branch did build 42 run with?
when did deploy start failing?
compare build 41 and 42 of deploy
where did the pipeline take this template file from?
```

## Example: browse, fix, replay

One failed build, from finding it to running a fix once. Use two windows:
a **terminal** for `jenkins browse` and `jenkins replay`, which are
interactive and only you run, and **Claude Code** for the investigation and
the fix.

Don't run these two with `!` inside Claude Code. The full-screen view and the
`[y/N]` question need a real terminal.

**1. Terminal: find and fetch the build**

```bash
jenkins browse
```

Go to the job with the arrows and Enter, select the failed build and press
`f`. It saves the build, for example to
`~/jenkins-investigations/deploy-42/`. `q` quits.

**2. Claude Code: why did it fail?**

```
/jenkins-fetch why did deploy 42 fail? files are in ~/jenkins-investigations/deploy-42/
```

The folder or the build URL is enough. If the folder already exists, the
agent reads it instead of fetching again. It reports the stage, the error
line in `pipeline.log`, the line in `pipeline.groovy` and any parameter that
explains it. It also tells you when Replay can't help: a wrong parameter
value, or a problem in the job config (`config.xml`), because Replay re-runs
the same parameters and job config.

**3. Claude Code: fix it**

```
propose a fix
```

The agent shows one change as a diff and asks. Say yes and it edits
`~/jenkins-investigations/deploy-42/pipeline.groovy`. Nothing is sent to
Jenkins. Then it gives you the command to run, and warns you if the pipeline
deploys or changes something.

**4. Terminal: run it, once**

```bash
jenkins replay https://jenkins.example.internal/job/team/job/deploy/42/
```

```console
Changes compared with #42:
--- #42 (Jenkins)
+++ pipeline.groovy (local)
@@ ...
-        sh 'make build'
+        sh 'make build TARGET=linux'

Parameters (same as #42, Replay can't change them):
  BRANCH = main

WARNING: Replay runs the pipeline for real, every stage, like Build Now.

Replay #42 with these changes? [y/N]: y

Started    : #43  https://jenkins.example.internal/job/team/job/deploy/43/
Following log (Ctrl+C stops watching, the build keeps running)
...
Result     : SUCCESS  (3m 12s)
Output     : /Users/you/jenkins-investigations/deploy-43/

Reminder   : this change is not in git yet. Commit it to the Jenkinsfile, or the next normal build fails again.
```

Replay has to be turned on for that Jenkins first: `allow_replay: true` in
the [configuration](configuration.md).

**5. Claude Code: check the result**

```
check the replay, build 43
```

The agent reads `deploy-43/`.
- **SUCCESS:** it reminds you to commit the fix, and names the repo and
  Jenkinsfile path from `config.xml`.
- **FAILURE:** it reports the new error and **stops**. For another try, ask
  "propose a fix" again. That fix goes into `deploy-43/pipeline.groovy`, and
  you replay build 43. Every try is one request from you: the agent never
  loops on its own.

**Without browse:** if you have the URL, skip step 1 and start with
`/jenkins-fetch <build-url>`. The agent fetches it itself, because fetching is
read-only.

## What it stops the agent doing

These are the failures the skill exists to prevent:

- **Inventing jobs, builds or instances.** Instances come from
  `~/.jenkins-cli/config.yaml`, jobs and builds from the URLs you give it. No
  URL, no guess: it asks.
- **Hardcoding a port or host.** The CLI picks a free local port and opens the
  tunnel itself, every time.
- **Touching your token.** It never reads, prints or copies the API token, and
  never asks the Keychain for it.
- **Trusting the defaults.** `params.json` marks each value as `build` (what
  the build really ran with) or `default` (only the job's default). The skill
  trusts the console log over both.
- **Reading a whole log into the conversation.** It works with `grep` on the
  saved files: result, errors, stages, checked-out commits.
- **Overwriting an earlier fetch.** If the folder exists it asks you first:
  overwrite, or keep both.
- **Skipping the report.** After every fetch you get the same short report:
  did it work, how it connected, the verified folder path, the files with
  their sizes, the result and the parameters.

## What it will not do

It will not create or edit your config. `jenkins init` is yours to run: it
asks for your API token and decides which Jenkins and AWS accounts an agent
can reach, and that is not a decision to delegate.

It will not change anything on Jenkins. It never triggers, replays, stops or
deletes a build, whatever is asked, and never calls Jenkins except through the
CLI. The CLI has no trigger command at all.

It can help with a Replay, but not run it. It finds the cause, proposes one
change to the fetched `pipeline.groovy`, edits it after you agree, and gives
you `jenkins replay <build-url>` to run yourself. `replay` refuses to run
without a terminal, so an agent can't confirm it. One fix per request, no loop.

It does not run `jenkins browse`. That is a full-screen view for you; the agent
uses `builds` and `fetch` instead.

It also cannot install the CLI, log you into AWS, or approve an SSO browser
prompt. When a login opens a browser, it tells you and waits.
