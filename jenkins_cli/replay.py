"""`jenkins replay`: run a build again with an edited Jenkinsfile, once.

One POST (to <build>/replay/run, see api.replay_post), then GETs only: wait for
the new build, follow its log, fetch it like `jenkins fetch`. No retries.
"""

from __future__ import annotations

import difflib
import re
import time
from pathlib import Path

from .api import Jenkins, JenkinsError

_STAGE = re.compile(r"^\[Pipeline\] \{ \((.+)\)\s*$")
_ERROR = re.compile(r"\bERROR:")


def diff(original: str, edited: str, build_label: str, local: Path, color: bool = False) -> list[str]:
    """Unified diff of the script Jenkins has vs the local file; [] when they are the same."""
    lines = list(difflib.unified_diff(original.splitlines(), edited.splitlines(),
                                      f"{build_label} (Jenkins)", f"{local.name} (local)", lineterm=""))
    if not color:
        return lines
    paint = {"+": "\033[32m", "-": "\033[31m", "@": "\033[36m"}
    return [f"{paint[ln[0]]}{ln}\033[0m" if ln[:1] in paint and not ln.startswith(("+++", "---")) else ln
            for ln in lines]


def build_params(jk: Jenkins, build: str) -> tuple[str | None, list[tuple[str, object]]]:
    d = jk.json(build, tree="result,actions[parameters[name,value]]")
    params = [(p["name"], p.get("value")) for a in d.get("actions", []) or []
              for p in (a or {}).get("parameters", []) or []]
    return d.get("result"), params


def next_number(jk: Jenkins, job: str) -> int:
    return jk.json(job, tree="nextBuildNumber")["nextBuildNumber"]


def wait_for_build(jk: Jenkins, job: str, first: int, original: int, timeout: int = 600, log=print) -> int:
    """The number of the build started by our replay: first build >= `first` caused by 'Replayed #<original>'."""
    want = f"Replayed #{original}"
    n, waited, said = first, 0, False
    while waited < timeout:
        try:
            d = jk.json(f"{job}/{n}", tree="number,actions[causes[shortDescription]]")
        except JenkinsError as exc:
            if not str(exc).startswith("not found"):
                raise
            if not said:
                log("Queued, waiting for the build to start...")
                said = True
            time.sleep(3)
            waited += 3
            continue
        causes = [c.get("shortDescription", "") for a in d.get("actions", []) or []
                  for c in (a or {}).get("causes", []) or []]
        if want in causes:
            return n
        n += 1  # someone else's build took this number; ours comes after it
    raise JenkinsError(f"the replay was sent, but no build '{want}' started within {timeout // 60} min - check the job page")


def follow(jk: Jenkins, build: str, out=print) -> bool:
    """Print the console log while the build runs. False if the user stopped watching (Ctrl+C)."""
    start = 0
    try:
        while True:
            text, start, more = jk.log_chunk(build, start)
            if text:
                out(text.rstrip("\n"))
            if not more:
                return True
            time.sleep(2)
    except KeyboardInterrupt:
        return False


def final_result(jk: Jenkins, build: str) -> tuple[str, int]:
    """(result, duration ms); the result can lag the end of the log by a moment."""
    for _ in range(5):
        d = jk.json(build, tree="result,duration")
        if d.get("result"):
            return d["result"], d.get("duration") or 0
        time.sleep(2)
    return "IN_PROGRESS", 0


def where_it_failed(log_file: Path) -> tuple[str | None, int | None, str | None]:
    """(stage, line number, line) of the first ERROR in a saved pipeline.log."""
    stage = None
    try:
        lines = log_file.read_text(errors="replace").splitlines()
    except OSError:
        return None, None, None
    for i, line in enumerate(lines, 1):
        m = _STAGE.match(line)
        if m:
            stage = m.group(1)
        elif _ERROR.search(line):
            return stage, i, line.strip()
    return stage, None, None


def duration(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60}m {s % 60}s" if s >= 60 else f"{s}s"
