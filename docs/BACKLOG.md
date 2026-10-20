# jenkins-cli backlog

Ideas that are not built yet. Each one says why, so a later decision has the
reasoning.

Shipped so far: `init`, `status`, `fetch`, `builds`, `browse`, `skill`,
`update`, tunnels with plain SSM fallback, several Jenkins servers, the
read-only lock.

## Worth doing next

### 1. Live log for running builds
`browse` shows a running build's log as it was when opened. Jenkins can send
only the new part (`logText/progressiveText?start=<offset>`), so following a
running build costs one small request every few seconds, and only while that
screen is open. Not built yet because it is the first thing that would poll.

### 2. `jenkins log <build-url> --grep <pattern>`
Search one build's log without saving all four files. Handy from an agent.
Same cost as `l` in `browse`.

### 3. `jenkins compare <build-a> <build-b>`
Parameters, Jenkinsfile and checked-out commits side by side. Today the agent
skill does it by fetching both and running `diff`.

### 4. A clear error when a URL matches no instance
Today a URL whose host is not in the config silently uses `default`, which
then answers `not found`. Saying "no instance for host X" would be clearer.

### 5. Job folder in the output folder name
`team-a/deploy/42` and `team-b/deploy/42` both save to `deploy-42/`. Including
the folder path avoids that, at the cost of longer names.

### 6. `update` asks first, and handles a local checkout
Ask `[y/N]` before reinstalling, and for an editable install run
`git pull --ff-only` first, refusing on uncommitted changes.

## Considered and left out

- **Triggering, rebuilding or stopping builds.** The tool is read-only on
  purpose, and enforced in code. An agent that can read builds should not be
  able to start them. The single exception is `jenkins replay`: off by
  default, terminal only, asks every time.
- **Auto-refresh in `browse`.** Every refresh is a request for every open
  screen. A key (`r`) does the same, only when you want it.
- **Loading a job's whole history at once.** `allBuilds` without a range makes
  Jenkins load every build record. Pages of 15 (browse) or 20 (builds) do not.

## Known limits, by choice

- Read-only: GET only, action URLs refused. Only `jenkins replay` POSTs, to `<build>/replay/run`.
- No daemon and no state of its own; `tunnels` keeps its tunnels, plain SSM
  sessions close with the command.
- macOS first, because of the Keychain.
