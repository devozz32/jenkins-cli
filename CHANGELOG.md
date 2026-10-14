# Changelog

## [Unreleased]

## [0.2.1] - 2026-10-14

### Docs
- New layout like the `tunnels` repo: short README, and `docs/` with install,
  configuration, how it works, agent skill, troubleshooting and backlog.
- `LICENSE` file added (MIT).
- Install commands point at `github.com/devozz32/jenkins-cli`.

### Fixed
- `jenkins update` says "no release published yet" (or "cannot reach GitHub")
  instead of a traceback.

## [0.2.0] - 2026-10-14

### Added
- `jenkins browse`: Jenkins in the terminal. Folders, jobs, the last 15 builds
  (more on demand, down to #1), stages, parameters, log with search, the
  Jenkinsfile, and `f` to save a build. One cached request per screen; the
  request count is shown and printed on exit.
- `jenkins builds <job-url>`: a job's history, one page per request
  (`-n`, `-p`).
- Build "started by" shows every cause, e.g. `Rebuilt #484 · jdoe`.

### Security
- Read-only lock in the API client: GET only, URLs that name a Jenkins action
  (`build`, `stop`, `doDelete`, `replay/run`, ...) are refused before anything
  is sent, and at most about 5 requests per second.

## [0.1.0] - 2026-10-14

### Added
- `jenkins init`, `status`, `fetch` (`--skip-aborted`, `-o`, `-f`),
  `skill`, `update`, `--version`.
- Connects through the `tunnels` CLI when configured, with an automatic
  fallback to plain AWS SSM; `Connection :` shows the way used.
- Several Jenkins servers in one config, picked by `-i`, the URL's host or
  `default`.
- API token in the macOS Keychain.
- Claude Code skill `/jenkins-fetch`, shipped in the package.
- Logo on `jenkins`, `--help`, `status` and `init` when a terminal is attached.
