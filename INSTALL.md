# Installing jenkins-cli

This guide takes you from zero to your first `jenkins fetch`.

1. [Requirements](#1-requirements)
2. [What is pipx?](#2-what-is-pipx)
3. [Install](#3-install)
4. [Set up: `jenkins init`](#4-set-up-jenkins-init)
5. [Test: `jenkins status`](#5-test-jenkins-status)
6. [AWS SSO login](#6-aws-sso-login)
7. [Optional: use the `tunnels` CLI](#7-optional-use-the-tunnels-cli)
8. [Claude Code skill: `/jenkins-fetch`](#8-claude-code-skill-jenkins-fetch)
9. [Update and uninstall](#9-update-and-uninstall)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Requirements

| Requirement | Why | Install / check |
|---|---|---|
| **macOS** | The token is stored in the macOS Keychain | — |
| **Python 3.9+** | The CLI is written in Python | `python3 --version` |
| **pipx** | Installs the CLI (see below) | `brew install pipx && pipx ensurepath` |
| **AWS CLI v2** | Opens the SSM session | `aws --version` |
| **AWS Session Manager plugin** | Needed by the AWS CLI for port forwarding | `brew install --cask session-manager-plugin` |
| **AWS access** | A profile allowed to start SSM sessions on the jump host | `aws sts get-caller-identity --profile <profile>` |
| **Jenkins API token** | To call the Jenkins API | Jenkins → your user → **Configure** → **API Token** → **Add new Token** |
| `tunnels` CLI *(optional)* | Keeps the tunnel up between commands | see [section 7](#7-optional-use-the-tunnels-cli) |

You also need three values from whoever manages your AWS/Jenkins setup:

- the **Jenkins URL**
- the **AWS profile and region** that can reach it
- the **SSM jump host** instance ID (`i-...`). `jenkins init` can list the online ones for you.

---

## 2. What is pipx?

**pipx** installs **Python command-line tools**.

- Each tool gets its **own private Python environment**, so tools never break each other's libraries.
- The command is placed in `~/.local/bin/`, so it works **from any folder**.

```bash
pipx install <source>         # install a tool
pipx list                     # see installed tools
pipx reinstall jenkins-cli    # reinstall (this is what "jenkins update" does)
pipx uninstall jenkins-cli    # remove it
```

After installing pipx for the first time, run `pipx ensurepath` and **open a new
terminal** so `~/.local/bin` is on your `PATH`.

---

## 3. Install

**From GitHub (normal users):**

```bash
pipx install git+https://github.com/<owner>/jenkins-cli.git
```

**From a local folder (developing the CLI):**

```bash
pipx install --editable /path/to/jenkins-cli
```

`--editable` runs the code straight from the folder, so changes take effect
without reinstalling.

Check it worked:

```bash
jenkins --version
```

---

## 4. Set up: `jenkins init`

```bash
jenkins init
```

It asks a few questions and writes `~/.jenkins-cli/config.yaml`:

| Prompt | Example answer | Notes |
|---|---|---|
| Name for this Jenkins instance | `main` | Any short name. Use a different name for each Jenkins server. |
| Jenkins URL | `https://jenkins.example.com` | |
| Jenkins user | `jdoe` | Your Jenkins username |
| API token | *(paste)* | Saved in the macOS Keychain, **not** in the config file. You are asked twice. |
| tunnels target | `myenv/jenkins` or empty | Only shown if `tunnels` is installed. Leave empty to skip. |
| Configure plain AWS SSM fallback? | `y` | Recommended, so it works even without `tunnels` |
| AWS profile | `my-aws-profile` | Profiles from `~/.aws/config` are listed |
| AWS region | `eu-west-1` | |
| SSM instance (jump host) | `i-0123456789abcdef0` | Online instances are listed for you |
| Output folder for fetched builds | `~/jenkins-investigations` | Where `jenkins fetch` saves builds |

Run `jenkins init` again at any time to change values, or
`jenkins init --name other` to add another Jenkins server.

---

## 5. Test: `jenkins status`

```bash
jenkins status
```

Expected output:

```
Config     : /Users/you/.jenkins-cli/config.yaml
Instance   : main (https://jenkins.example.com)
Output dir : /Users/you/jenkins-investigations
Starting SSM tunnel 127.0.0.1:53122 -> jenkins.example.com:443 ...
Connection : ssm
Local port : 53122
Jenkins    : OK as jdoe
```

Then fetch your first build:

```bash
jenkins fetch https://jenkins.example.com/job/my-job/42/
```

---

## 6. AWS SSO login

The SSM tunnel needs a valid AWS session.

- If your SSO session has expired, `jenkins` runs **`aws sso login`** for you.
- A **browser opens and you approve it**. This step can't be automated; it's how SSO works.

**Tip: get logged out less often.** Profiles written in the older format
(`sso_start_url` directly on the profile) have no refresh token, so the login
expires every few hours. The newer format uses an `[sso-session]` block and
renews silently in the background:

```ini
[sso-session my-sso]
sso_start_url = https://my-company.awsapps.com/start
sso_region = eu-west-1
sso_registration_scopes = sso:account:access

[profile my-aws-profile]
sso_session = my-sso
sso_account_id = 123456789012
sso_role_name = MyRole
region = eu-west-1
```

You keep the same identity and permissions. Back up `~/.aws/config` before changing it.

---

## 7. Optional: use the `tunnels` CLI

[`tunnels`](https://github.com/Zivgl66/tunnels) manages SSM tunnels from its own
config and keeps them up between commands. With it, repeated `jenkins` commands
start faster and reuse the same tunnel.

1. Install and set it up:
   ```bash
   pipx install git+https://github.com/Zivgl66/tunnels.git
   tunnels init
   ```
2. Add a **host target** for Jenkins to the `tunnels` config
   (`tunnels config` opens it): the jump host forwards to your Jenkins host on port 443.
   Copy the shape of an existing host/database target in that file.
3. Check it: `tunnels up <env> jenkins`, then `tunnels status`.
4. Run `jenkins init` again and enter `<env>/jenkins` as the **tunnels target**.

`jenkins status` should now show `Connection : tunnels (<env>/jenkins)`.
Keep the `ssm` block in the config as a fallback. `tunnels` is always tried
first; the CLI switches to plain SSM by itself when:

- `tunnels` is not installed: `NOTE: tunnels_target is set but the 'tunnels' CLI is not installed - using plain SSM.`
- `tunnels` can't bring the tunnel up: `WARNING: tunnels failed: ... Falling back to plain SSM.`

`Connection :` always shows the way that was actually used. Without an `ssm`
block there is no fallback, and the `tunnels` error is shown.

---

## 8. Claude Code skill: `/jenkins-fetch`

The package includes a [Claude Code](https://claude.com/claude-code) skill
that teaches Claude to use this CLI: fetch a build, then investigate the saved
files (why it failed, what parameters it ran with, which repos and branches it
checked out).

```bash
jenkins skill install      # copies the skill to ~/.claude/skills/jenkins-fetch/
jenkins skill              # shows whether it is installed and where
jenkins skill uninstall    # removes it
```

Restart Claude Code after installing. Then either call it directly:

```
/jenkins-fetch https://jenkins.example.com/job/my-job/42/
```

or just paste a Jenkins build URL and ask a question ("why did this fail?");
Claude picks the skill up on its own.

- The skill runs the same `jenkins` commands you would. It is read-only, never
  edits your config, and never reads your API token.
- If your AWS SSO session has expired, approve the browser login when it opens.
- `jenkins update` also refreshes the installed skill, so it always matches
  your CLI version.
- Editing the skill yourself? Use `jenkins skill install --link` from an
  `--editable` install, so changes to `jenkins_cli/skills/jenkins-fetch/SKILL.md`
  apply immediately.

---

## 9. Update and uninstall

```bash
jenkins --version          # installed version
jenkins update --check     # is there a newer release?
jenkins update             # install it
```

Remove everything:

```bash
jenkins skill uninstall
pipx uninstall jenkins-cli
rm -rf ~/.jenkins-cli
security delete-generic-password -s jenkins-cli -a jenkins-main   # one per instance name
```

---

## 10. Troubleshooting

| Message | Cause | Fix |
|---|---|---|
| `jenkins: command not found` | `~/.local/bin` not on `PATH` | `pipx ensurepath`, then open a new terminal |
| `no config file at ... run: jenkins init` | Not set up yet | `jenkins init` |
| `no Keychain item for ...` | Token not stored | `jenkins init` and replace the token |
| `the AWS Session Manager plugin is not installed` | Missing plugin | `brew install --cask session-manager-plugin` |
| `AWS profile ... has no valid credentials` | Not an SSO profile, or keys expired | Fix the profile in `~/.aws/config` |
| `SSM tunnel did not come up within 30s` | Wrong instance/region, no SSM permission, or the jump host can't reach Jenkins | Check `aws ssm describe-instance-information --profile <p> --region <r>` |
| `HTTP 401` / `HTTP 403` | Wrong user/token, or no permission on that job | Create a new API token, run `jenkins init` |
| `not found: /job/...` | Wrong URL | Copy the URL from the Jenkins UI |
| `local port N is already in use` | A fixed `local_port` is taken | Set `local_port: auto` |
| `tunnels_target is set but the 'tunnels' CLI is not installed` | `tunnels` removed. As a NOTE it still works over SSM; as an ERROR there is no `ssm` block | Install it, or add the `ssm` block (`jenkins init`) |
| `WARNING: tunnels failed: ... Falling back to plain SSM.` | The `tunnels` target is wrong or its tunnel won't start; the command still works over SSM | `tunnels up <env> <target>` and `tunnels logs <env> <target>` to see why |
| `/jenkins-fetch` is not offered in Claude Code | Skill not installed, or Claude Code not restarted | `jenkins skill install`, then restart Claude Code |
| `the GitHub repo is not set yet` | Development build without a release source | Reinstall from GitHub |
