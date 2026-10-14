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

It will not change anything on Jenkins. The CLI is read-only by design: it
sends only GET requests and refuses any URL that names a Jenkins action, so
no build is triggered, replayed, stopped or deleted, whatever is asked.

It does not run `jenkins browse`. That is a full-screen view for you; the agent
uses `builds` and `fetch` instead.

It also cannot install the CLI, log you into AWS, or approve an SSO browser
prompt. When a login opens a browser, it tells you and waits.
