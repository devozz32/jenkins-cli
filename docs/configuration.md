# Configuration

`jenkins init` writes `~/.jenkins-cli/config.yaml`. Set `JENKINS_CLI_CONFIG`
to use another path. Every company value lives in this file, never in the code.

```yaml
default: main
output_dir: ~/jenkins-investigations     # where fetch saves builds

instances:
  main:
    url: https://jenkins.example.internal
    user: your-jenkins-user
    token: keychain:jenkins-main         # a reference, not the token
    tunnel:
      tunnels_target: dev/jenkins        # optional: use the tunnels CLI
      ssm:                               # plain SSM: the fallback, or the only way
        profile: <aws-profile>
        region: <aws-region>
        instance: <ssm-instance-id>
        local_port: auto
```

A commented copy: [`jenkins_cli/config.example.yaml`](../jenkins_cli/config.example.yaml).

## Keys

| Key | Required | Meaning |
| --- | --- | --- |
| `default` | no | Instance used when nothing else picks one. Default: the first |
| `output_dir` | no | Where `fetch` (and `f` in `browse`) saves builds. Default `~/jenkins-investigations`. Shared by all instances |
| `instances.<name>.url` | yes | Jenkins base URL |
| `instances.<name>.user` | yes | Your Jenkins user name |
| `instances.<name>.token` | yes | `keychain:<item>` or `env:<VAR>`. See [the token](#the-token) |
| `instances.<name>.allow_replay` | no | `true` lets `jenkins replay` send an edited Jenkinsfile to this Jenkins. Default: off. Set it by hand; `init` never asks, and keeps it when re-run |
| `tunnel.tunnels_target` | one of the two | `<env>/<target>` in the [`tunnels`](https://github.com/Zivgl66/tunnels) config |
| `tunnel.ssm.profile` | one of the two | AWS profile from `~/.aws/config` |
| `tunnel.ssm.region` | with `ssm` | Region of the jump host |
| `tunnel.ssm.instance` | with `ssm` | Jump host instance ID (`i-...`), with a running SSM agent |
| `tunnel.ssm.remote_host` | no | Host the jump host forwards to. Default: the host in `url` |
| `tunnel.ssm.remote_port` | no | Default `443` |
| `tunnel.ssm.local_port` | no | `auto` (a free port each time, the default) or a fixed number |

An instance needs `tunnels_target`, `ssm`, or both. With both, `tunnels` is
tried first and `ssm` is the fallback: see
[how it works](how-it-works.md#two-ways-to-connect).

## The token

The file never holds the API token, only where to find it:

- `keychain:jenkins-main` is the macOS Keychain item with service
  `jenkins-cli` and account `jenkins-main`. `jenkins init` creates it and
  lets `security` ask for the token itself, so it never shows up in your shell
  history or in a process list.
- `env:JENKINS_TOKEN` reads an environment variable instead, for a CI job or a
  machine without a Keychain.

Make the token in Jenkins: your user → **Configure** → **API Token** → **Add
new Token**. To replace it, run `jenkins init` again and answer `y` to
*Replace the stored API token?*

## Several Jenkins servers

One file can hold any number of servers, each with its own URL, user, token,
AWS account and jump host. Add one with a new name; the existing ones are kept:

```bash
jenkins init --name prd
```

```yaml
default: dev
instances:
  dev:
    url: https://jenkins-dev.example.internal
    user: your-user
    token: keychain:jenkins-dev
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

Which one a command uses, first match wins:

1. `-i <name>`: `jenkins -i prd status`.
2. The instance whose `url` host matches the URL you pass. Paste a prod build
   URL into `fetch`, `builds` or `browse` and it uses the prod account, tunnel
   and token.
3. `browse` with no URL asks you to pick one from a numbered list.
4. `default`. This is what `status` uses.

The CLI only knows the servers in this file. It does not go looking for others.

All instances share one `output_dir`. A dev and a prod job with the same name
and build number land in the same folder; you are asked before anything is
overwritten, or use `-o` to keep them apart.

## The tunnels target

To let `jenkins` reuse a tunnel from the [`tunnels`](https://github.com/Zivgl66/tunnels)
CLI, add a host target for Jenkins to the environment block of the account
that can reach it (`tunnels config` opens the file):

```yaml
dev-account:
  profile: <aws-profile>
  region: <aws-region>
  targets:
    jenkins:
      host: jenkins.example.internal     # no https://
      port: 443
      jump: <ssm-instance-id>
```

Check it with `tunnels up dev-account jenkins`, then set
`tunnels_target: dev-account/jenkins` with `jenkins init`.
`jenkins status` should show `Connection : tunnels (dev-account/jenkins)`.

Do the same in each account's block when you have several Jenkins servers.

## Ports

With plain SSM, `local_port: auto` picks a free port every time, so nothing
else on your machine is ever disturbed. A fixed port that is already taken
stops with `local port N is already in use` instead of killing whatever holds
it.

With `tunnels`, the port is whatever `tunnels` chose; `jenkins` reads it from
`~/.tunnels/state.json`.
