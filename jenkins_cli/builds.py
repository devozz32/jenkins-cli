"""List a job's build history, one page per request (read-only)."""

from __future__ import annotations

import time

from .api import Jenkins, JenkinsError

FIELDS = "number,result,building,timestamp,duration,actions[causes[shortDescription,userName]]"

COLORS = {"SUCCESS": "32", "FAILURE": "31", "UNSTABLE": "33", "ABORTED": "90", "NOT_BUILT": "90", "RUNNING": "36"}


def page(jk: Jenkins, job: str, number: int = 1, size: int = 20) -> dict:
    """Builds newest first. Page 1 = the newest `size` builds. Only that page is loaded."""
    start = (number - 1) * size
    d = jk.json(job, tree=f"firstBuild[number],lastBuild[number],allBuilds[{FIELDS}]{{{start},{start + size}}}")
    if "allBuilds" not in d:
        raise JenkinsError(f"{job} is not a job with builds (a folder or view?)")
    return d


def result_of(b: dict) -> str:
    return "RUNNING" if b.get("building") else (b.get("result") or "NOT_BUILT")


def started_by(b: dict) -> str:
    """All causes, e.g. 'Rebuilt #484 · jdoe' or 'timer'. User names come last."""
    reasons, users = [], []
    for action in b.get("actions") or []:
        for cause in (action or {}).get("causes") or []:
            if cause.get("userName"):
                users.append(cause["userName"])
                continue
            desc = cause.get("shortDescription") or ""
            if desc.startswith("Started by user "):
                users.append(desc[len("Started by user "):])
            elif desc:
                reasons.append(desc[len("Started by "):] if desc.startswith("Started by ") else desc)
    return " · ".join(dict.fromkeys(reasons + users))


def duration(b: dict) -> str:
    ms = b.get("duration") or 0
    if b.get("building"):
        ms = time.time() * 1000 - (b.get("timestamp") or 0)
    s = int(ms // 1000)
    if s >= 3600:
        return f"{s // 3600}h{s % 3600 // 60:02d}m"
    return f"{s // 60}m{s % 60:02d}s"


def started(b: dict) -> str:
    ts = b.get("timestamp")
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts / 1000)) if ts else ""


def table(builds: list[dict], color: bool) -> list[str]:
    def paint(result: str) -> str:
        text = f"{result:<9}"
        return f"\033[{COLORS[result]}m{text}\033[0m" if color and result in COLORS else text

    rows = [f"{'BUILD':<7} {'RESULT':<9} {'STARTED':<16}  {'TIME':>7}  STARTED BY"]
    for b in builds:
        by = started_by(b)
        rows.append(f"{'#' + str(b['number']):<7} {paint(result_of(b))} {started(b):<16}  {duration(b):>7}  "
                    f"{by[:60] + '...' if len(by) > 60 else by}")
    return rows
