# Troubleshooting

| What you see | What it means | What to do |
| --- | --- | --- |
| `jenkins: command not found` | `~/.local/bin` is not on your `PATH` | `pipx ensurepath`, then open a new terminal |
| `no config file at ... run: jenkins init` | Not set up yet | `jenkins init` |
| `unknown instance 'x'. Known: ...` | `-i` names a server that is not in the config | Use one of the names listed, or `jenkins init --name x` |
| `no Keychain item for '...'` | The token is not stored | `jenkins init`, and replace the token |
| `the AWS Session Manager plugin is not installed` | Missing plugin | `brew install --cask session-manager-plugin` |
| `AWS session for '...' expired - starting 'aws sso login'` | SSO session ran out | Approve the login in the browser that opens |
| `AWS profile '...' has no valid credentials` | Not an SSO profile, or its keys expired | Fix the profile in `~/.aws/config` |
| `SSM tunnel did not come up within 30s` | Wrong jump host or region, no SSM permission, or the jump host cannot reach Jenkins | `aws ssm describe-instance-information --profile <p> --region <r>` should list the jump host as Online |
| `local port N is already in use` | A fixed `local_port` is taken | Set `local_port: auto` |
| `NOTE: tunnels_target is set but the 'tunnels' CLI is not installed` | `tunnels` is gone; the command still runs over plain SSM | Install `tunnels`, or remove `tunnels_target` |
| `WARNING: tunnels failed: ... Falling back to plain SSM.` | The `tunnels` target is wrong or its tunnel will not start; the command still runs | `tunnels up <env> <target>` and `tunnels logs <env> <target>` show why |
| `tunnels_target is set but ... no tunnel.ssm fallback` | `tunnels` is missing and there is nothing to fall back to | Install `tunnels`, or add the `ssm` block with `jenkins init` |
| `HTTP 401` / `HTTP 403` | Wrong user or token, or no permission on that job | Make a new API token, run `jenkins init` |
| `not found: /job/...` | Wrong URL, or the build was deleted | Copy the URL from the Jenkins website |
| `WARN: could not fetch config.xml` | No Extended Read permission on the job | The other three files are still saved |
| `Could not extract Jenkinsfile` | Not a pipeline, or no permission to see Replay | The other three files are still saved |
| `... already exists (use --force to overwrite)` | A folder from an earlier fetch | `-f` to overwrite, or `-o <dir>` to keep both |
| `refused: '...' changes Jenkins and this CLI is read-only` | A URL named a Jenkins action (`build`, `stop`, ...) | Working as intended. Pass the job or build URL, not an action URL |
| `... is not a job with builds (a folder or view?)` | `builds` got a folder URL | Pass a job URL, or use `jenkins browse <folder-url>` |
| `browse needs an interactive terminal` | `browse` was piped or run by a script | Run it in a terminal; scripts use `builds` and `fetch` |
| `(no stage data ...)` in `browse` | Freestyle job, or the Pipeline Stage View plugin is missing | Use `l` for the log |
| `/jenkins-fetch` not offered in Claude Code | Skill not installed, or the session started before it was | `jenkins skill install`, then restart Claude Code |
| `the GitHub repo is not set yet` | A development build with no release source | Reinstall from GitHub |

## Known limits

- **No live log.** `browse` shows a running build's log up to the moment you
  opened it. `r` loads it again.
- **The whole log or nothing.** `l` and `fetch` download one build's full log;
  there is no "last N lines" yet.
- **Deep history costs more.** The newest pages are cheap; paging thousands of
  builds back makes Jenkins read every build record on the way.
- **One `output_dir` for all instances.** Same job name and build number on two
  servers means the same folder. You are asked before overwriting.
- **Folder names use only the last job name.** `team-a/deploy/42` and
  `team-b/deploy/42` would share `deploy-42/`.
- **macOS only.** The token lives in the Keychain. `env:<VAR>` tokens work
  elsewhere, but nothing else is tested there.
