"""The logo shown at the top of `jenkins`, `--help`, `status` and `init`.

Printed only when stdout is a terminal, so scripts, pipes and Claude Code
never see it. Colors are skipped when NO_COLOR is set or TERM=dumb.
"""

from __future__ import annotations

import os
import sys

from . import __version__

HORN = "1;38;5;196"   # bright red
FACE = "38;5;160"     # red
EYE = "1;38;5;226"    # bold yellow
GRIN = "38;5;231"     # white teeth
BEARD = "38;5;52"     # dark red
TIE = "1;38;5;232"    # black
SUIT = "38;5;88"      # deep red
SHIRT = "38;5;255"    # white
TITLE = "1;38;5;196"  # bold red
DIM = "38;5;245"      # grey text


def _color_ok(stream) -> bool:
    return not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb" and stream.isatty()


def render(color: bool = True) -> str:
    def c(code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if color else text

    lines = [
        "    " + c(HORN, "(\\") + "          " + c(HORN, "/)"),
        "     " + c(HORN, "\\\\") + c(FACE, ".-~~~~-.") + c(HORN, "//"),
        "     " + c(FACE, "/  ") + c(EYE, "\\    /") + c(FACE, "  \\") + "     "
        + c(TITLE, "jenkins-cli") + " " + c(DIM, __version__),
        "    " + c(FACE, "|   ") + c(EYE, "@    @") + c(FACE, "   |") + "    " + c(DIM, "fetch & inspect Jenkins builds"),
        "    " + c(FACE, "|     <>     |") + "    " + c(DIM, "through tunnels or AWS SSM"),
        "     " + c(FACE, "\\  ") + c(GRIN, "\\vvvv/") + c(FACE, "  /"),
        "      " + c(FACE, "'.") + c(BEARD, "  \\/  ") + c(FACE, ".'"),
        "    " + c(SUIT, "__/ ") + c(SHIRT, "\\") + c(TIE, "><") + c(SHIRT, "/") + c(SUIT, "  \\__"),
        "   " + c(SUIT, "/    ") + c(SHIRT, " |  | ") + c(SUIT, "    \\"),
    ]
    return "\n" + "\n".join(lines) + "\n"


def show(stream=None) -> None:
    """Print the logo if `stream` (default stdout) is an interactive terminal."""
    stream = stream or sys.stdout
    if not stream.isatty():
        return
    print(render(color=_color_ok(stream)), file=stream, flush=True)
