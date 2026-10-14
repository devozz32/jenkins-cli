"""`jenkins skill`: install the bundled Claude Code skill into ~/.claude/skills.

The skill ships inside the package, so every pipx install has a copy that
matches its CLI version. `install` copies it (or symlinks it with --link, for
working on the skill itself); `jenkins update` refreshes an installed copy.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

NAME = "jenkins-fetch"
SOURCE = Path(__file__).parent / "skills" / NAME
SKILLS_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "skills"
TARGET = SKILLS_DIR / NAME


def installed() -> bool:
    return TARGET.is_symlink() or TARGET.exists()


def install(link: bool = False) -> str:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    remove()
    if link:
        TARGET.symlink_to(SOURCE.resolve(), target_is_directory=True)
        return f"Linked {TARGET} -> {SOURCE.resolve()}"
    shutil.copytree(SOURCE, TARGET)
    return f"Installed {TARGET}"


def remove() -> bool:
    if TARGET.is_symlink() or TARGET.is_file():
        TARGET.unlink()
    elif TARGET.is_dir():
        shutil.rmtree(TARGET)
    else:
        return False
    return True
