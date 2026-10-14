"""`jenkins update`: install the latest GitHub release through pipx.

Same model as the tunnels CLI: the latest version comes from the GitHub
releases API, the install is a `pipx reinstall` (pipx remembers the git URL).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from urllib.request import Request, urlopen

from . import __version__, skill

PACKAGE = "jenkins-cli"
REPO = ""  # TODO: "<owner>/<repo>" once the GitHub repo exists


class UpdateError(Exception):
    pass


def _parse(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.lstrip("v").split("+")[0].split("."))
    except ValueError:
        return (0,)


def latest_release() -> str:
    if not REPO:
        raise UpdateError("the GitHub repo is not set yet (REPO in jenkins_cli/update.py)")
    req = Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                  headers={"Accept": "application/vnd.github+json"})
    with urlopen(req, timeout=15) as resp:
        return json.load(resp)["tag_name"]


def run(check_only: bool = False) -> int:
    latest = latest_release()
    print(f"installed: {__version__}   latest: {latest}")
    if _parse(latest) <= _parse(__version__):
        print("Already up to date.")
        return 0
    if check_only:
        return 0
    if not shutil.which("pipx"):
        raise UpdateError(f"pipx not found - install with: pipx install --force git+https://github.com/{REPO}.git")
    code = subprocess.run(["pipx", "reinstall", PACKAGE]).returncode
    if code == 0 and skill.installed() and not skill.TARGET.is_symlink():
        # The new version's own code copies its bundled skill over the old one.
        subprocess.run(["jenkins", "skill", "install"])
    return code
