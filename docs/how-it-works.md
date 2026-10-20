# How it works

```
jenkins ──► 127.0.0.1:<port> ──► AWS SSM session ──► jump host ──► Jenkins :443
```

Jenkins sits in a private network. The only way in is an SSM port forward
through a jump host, so every command does the same four things:

1. **Reads the config** and picks the Jenkins instance (`-i`, the URL's host,
   or `default`; see [configuration](configuration.md#several-jenkins-servers)).
2. **Gets a local port** that forwards to Jenkins: through `tunnels`, or its
   own SSM session.
3. **Calls the Jenkins REST API** on `https://127.0.0.1:<port>` with your user
   and the API token from the Keychain.
4. **Closes what it opened.** Its own SSM session is stopped when the command
   ends. A `tunnels` tunnel is left running, since `tunnels` owns it.

## Two ways to connect

| | With [`tunnels`](https://github.com/Zivgl66/tunnels) | Plain SSM |
| --- | --- | --- |
| Config | `tunnel.tunnels_target: <env>/<target>` | `tunnel.ssm: {profile, region, instance}` |
| What happens | Reads the port from `~/.tunnels/state.json`. If the tunnel is down, runs `tunnels up <env> <target>` | Runs `aws ssm start-session` with `AWS-StartPortForwardingSessionToRemoteHost` on a free port |
| AWS login | `tunnels` does it | `jenkins` does it (below) |
| Between commands | The tunnel stays up, so the next command starts at once | Opened and closed per command |
| `Connection :` line | `tunnels (<env>/<target>)` | `ssm` |

`tunnels` is optional. Set both and you get its speed with a fallback:

- `tunnels` **not installed**:
  `NOTE: tunnels_target is set but the 'tunnels' CLI is not installed - using plain SSM.`
- `tunnels up` **fails**, or its port never opens:
  `WARNING: tunnels failed: ... Falling back to plain SSM.`

Either way the command still runs, and `Connection :` shows the way that was
really used. Without an `ssm` block there is no fallback and you get the
`tunnels` error.

## AWS login

On the plain SSM path, `jenkins` first runs `aws sts get-caller-identity` for
the profile. If the session has expired and the profile is an SSO profile, it
runs `aws sso login` and a browser opens for you to approve. That step cannot
be automated; it is how SSO works. Nothing is read from or written to the AWS
token cache by `jenkins` itself.

Profiles in the older SSO format expire every few hours. The `[sso-session]`
format refreshes silently: see [install](install.md#6-aws-sso-login).

## Read-only, enforced

Every request goes through one method in `jenkins_cli/api.py`, and it checks
three things before anything is sent:

- **GET only.** The method is fixed and no request body is ever attached. The
  only POST in the code is a separate method for `jenkins replay`, below.
- **No action URLs.** A path that names a Jenkins action is refused with
  `refused: '<action>' changes Jenkins and this CLI is read-only`. The list
  covers `build`, `buildWithParameters`, `stop`, `kill`, `term`, `doDelete`,
  `replay/run`, `rebuild`, `configSubmit`, `disable`, `enable`, `script`,
  `input/.../proceed`, `abort`, `quietDown`, `restart` and more. A job that is
  only *named* `build` or `run` is still fine: names after `/job/` and `/view/`
  are never mistaken for actions.
- **Paced.** At least 0.2 s between requests, so never more than about 5 per
  second.

Reading the replay page (for the Jenkinsfile) is a GET of the form; nothing is
replayed.

### The one exception: `jenkins replay`

`replay_post()` in `api.py` is the only method that sends a POST. It accepts
exactly one shape of path, `<job>/<build-number>/replay/run`, and nothing else
(no `build`, no `buildWithParameters`, no `stop`). The command around it:

- refuses unless the instance has `allow_replay: true` in the config;
- refuses without a terminal, so a script or an agent can't confirm it;
- refuses when the local `pipeline.groovy` is the same as the build's script;
- shows the diff and the parameters (Replay keeps the original build's
  parameters), and asks `[y/N]`. There is no `--yes`;
- sends one POST, then only GETs: it finds the new build by its cause
  (`Replayed #<n>`), follows `logText/progressiveText` every 2 s, and saves the
  new build like `fetch`. It never retries.

## What each command asks Jenkins for

Every list asks only for the fields it shows (`tree=`), and long lists come in
pages, so a click costs one small request.

| Command / screen | Requests | Endpoint |
| --- | --- | --- |
| `status` | 1 | `/whoAmI/api/json` |
| `builds`, one page | 1 | `<job>/api/json?tree=allBuilds[...]{from,to}` |
| `fetch` | 5 (6 with a job URL) | `config.xml`, the job's and the build's `api/json`, `replay/`, `consoleText` |
| `browse`: a folder | 1 | `<folder>/api/json?tree=jobs[name,_class,color,url]` |
| `browse`: a job | 1 per 15 builds | as `builds` |
| `browse`: a build | 2 | `<build>/api/json`, `<build>/wfapi/describe` (stages) |
| `browse`: `l`, `j` | 1 each | `consoleText`, `replay/` |

`browse` keeps every screen it loaded, so going back costs nothing; `r`
reloads on purpose. There is no auto-refresh and no polling: a request is only
sent when you press a key. The bottom line counts the requests, and `q`
prints the total.

For comparison, opening a job page in a browser makes dozens of requests and
keeps refreshing the build history while it is open.

**The two heavier things.** `l` and `fetch` download the whole log of one
build, the same as **Console Output** in the website. And paging far back
through a job's history makes Jenkins read every build record down to that
page; a few pages are nothing, thousands of builds back is more work.

## What fetch saves

| File | Where it comes from |
| --- | --- |
| `config.xml` | `<job>/config.xml`. Needs the Extended Read permission; a warning, not a failure, without it |
| `params.json` | Three sources merged: the parameter definitions in `config.xml`, the job's `api/json`, and the values in the build's `api/json`. Each value is marked `source: build` (what the build ran with) or `source: default` (only the job's default) |
| `pipeline.groovy` | The `_.mainScript` field of the build's replay page: the script that build really ran, even if the Jenkinsfile in git has changed since |
| `pipeline.log` | `<build>/consoleText`, streamed to disk |

The folder is `<output_dir>/<last job name>-<build number>/`. An existing
folder with files in it is never overwritten without asking, or `-f`.
