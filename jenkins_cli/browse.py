"""`jenkins browse`: the Jenkins website, read-only, in the terminal (curses).

Folders -> jobs -> builds -> stages, parameters, log, Jenkinsfile. Every list is
loaded once with a single GET (`tree=` keeps it small) and cached, so moving
back and forth costs nothing. `r` reloads the current screen on purpose.
"""

from __future__ import annotations

import curses
import json
import locale
import os
import re
from pathlib import Path
from urllib.parse import unquote

from . import builds, fetch
from .api import Jenkins, JenkinsError

ITEM_TREE = "jobs[name,_class,color,url]"
BUILD_TREE = ("number,result,building,timestamp,duration,description,"
              "actions[causes[shortDescription,userName],parameters[name,value]]")
PAGE = 50
FOLDER_CLASSES = ("Folder", "MultiBranch", "OrganizationFolder")

# color pair numbers
GREEN, RED, YELLOW, GREY, CYAN, HEAD, MATCH = range(1, 8)

JOB_COLORS = {  # Jenkins 'color' -> (symbol, word, pair)
    "blue": ("✓", "ok", GREEN), "red": ("✗", "failed", RED), "yellow": ("!", "unstable", YELLOW),
    "aborted": ("⊘", "aborted", GREY), "notbuilt": ("·", "never run", GREY),
    "disabled": ("-", "disabled", GREY), "grey": ("·", "", GREY),
}
RESULT_PAIRS = {"SUCCESS": GREEN, "FAILURE": RED, "FAILED": RED, "UNSTABLE": YELLOW,
                "ABORTED": GREY, "NOT_BUILT": GREY, "RUNNING": CYAN, "IN_PROGRESS": CYAN}
RESULT_SYMBOLS = {"SUCCESS": "✓", "FAILURE": "✗", "FAILED": "✗", "UNSTABLE": "!", "ABORTED": "⊘",
                  "NOT_BUILT": "·", "RUNNING": "▶", "IN_PROGRESS": "▶", "NOT_EXECUTED": "·", "SKIPPED": "·"}
LOG_ERROR = re.compile(r"ERROR|FAILED|FAILURE|Exception|error:", re.IGNORECASE)
LOG_STAGE = re.compile(r"^\[Pipeline\] (\{ \(|stage)")


def wrap(value: str, width: int = 80) -> list[str]:
    """Split a long value into lines, breaking after commas or spaces where possible."""
    out: list[str] = []
    for line in value.splitlines() or [""]:
        cur = ""
        for token in re.split(r"(?<=[, ])", line):
            while len(token) > width:
                if cur:
                    out.append(cur)
                    cur = ""
                out.append(token[:width])
                token = token[width:]
            if len(cur) + len(token) > width:
                out.append(cur)
                cur = ""
            cur += token
        out.append(cur)
    return out


def is_folder(item: dict) -> bool:
    return any(k in item.get("_class", "") for k in FOLDER_CLASSES)


class Row:
    def __init__(self, text: str, pair: int = 0, open_=None, bold: bool = False):
        self.text, self.pair, self.open, self.bold = text, pair, open_, bold


# ─── views ──────────────────────────────────────────────────────────────────

class ListView:
    """A selectable list. Enter on a row calls its `open` (returns a new view, or None)."""

    keys = "Enter open  ← back  / filter  r reload  q quit"

    def __init__(self, title: str, load):
        self.title, self.load = title, load
        self.rows: list[Row] = []
        self.sel = self.top = 0
        self.filter = ""

    def visible(self) -> list[Row]:
        if not self.filter:
            return self.rows
        f = self.filter.lower()
        return [r for r in self.rows if f in r.text.lower()]

    def selectable(self) -> bool:
        return True


class TextView(ListView):
    """A scrollable text page (log, Jenkinsfile, build details) with search."""

    keys = "↑↓ PgUp PgDn g/G top/end  / search  n/N next/prev  ← back  q quit"

    def __init__(self, title: str, load, extra_keys: str = ""):
        super().__init__(title, load)
        self.search = ""
        if extra_keys:
            self.keys = extra_keys + "  " + self.keys

    def visible(self) -> list[Row]:
        return self.rows

    def selectable(self) -> bool:
        return False


# ─── the app ────────────────────────────────────────────────────────────────

class App:
    def __init__(self, scr, jk: Jenkins, base_url: str, header: str, out_dir: Path):
        self.scr, self.jk, self.base_url, self.header, self.out_dir = scr, jk, base_url, header, out_dir
        self.stack: list[ListView] = []
        self.msg = ""

    # loading ------------------------------------------------------------

    def push(self, view: ListView) -> None:
        if self.fill(view):
            self.stack.append(view)

    def fill(self, view: ListView) -> bool:
        self.msg = "Loading..."
        self.draw()
        try:
            view.rows = view.load()
            self.msg = ""
            return True
        except JenkinsError as exc:
            self.msg = f"Error: {exc}"
            return False

    # screens ------------------------------------------------------------

    def folder(self, path: str, title: str) -> ListView:
        def load():
            items = self.jk.json(path, tree=ITEM_TREE).get("jobs")
            if items is None:
                raise JenkinsError(f"{title} has no items")
            rows = []
            for it in sorted(items, key=lambda j: (not is_folder(j), j["name"].lower())):
                p = Jenkins.path_of(it.get("url") or f"{path.rstrip('/')}/job/{it['name']}")
                name = it["name"]
                if is_folder(it):
                    rows.append(Row(f"▸ {name}/", CYAN, lambda p=p, n=name: self.folder(p, f"{title.rstrip('/')}/{n}"),
                                    bold=True))
                else:
                    color = (it.get("color") or "grey")
                    running = color.endswith("_anime")
                    sym, word, pair = JOB_COLORS.get(color.replace("_anime", ""), ("·", "", GREY))
                    if running:
                        sym, word, pair = "▶", "running", CYAN
                    rows.append(Row(f"{sym} {name:<60} {word}", pair, lambda p=p, n=name: self.job(p, n)))
            return rows
        return ListView(title, load)

    def job(self, path: str, name: str) -> ListView:
        view = ListView(f"{name}  (builds)", None)
        state = {"page": 0, "first": None}

        def build_rows(d: dict) -> list[Row]:
            out = []
            for b in d["allBuilds"]:
                res = builds.result_of(b)
                out.append(Row(f"{RESULT_SYMBOLS.get(res, ' ')} #{b['number']:<6} {res:<10} {builds.started(b):<16}  "
                               f"{builds.duration(b):>7}  {builds.started_by(b)[:50]}",
                               RESULT_PAIRS.get(res, 0), lambda n=b["number"]: self.build(path, name, n)))
            return out

        def more_row() -> Row:
            return Row(f"   … older builds (next {PAGE})", GREY, load_more)

        def load_page() -> list[Row]:
            state["page"] += 1
            d = builds.page(self.jk, path, state["page"], PAGE)
            state["first"] = (d.get("firstBuild") or {}).get("number")
            rows = build_rows(d)
            last = d["allBuilds"][-1]["number"] if d["allBuilds"] else None
            if len(d["allBuilds"]) == PAGE and last != state["first"]:
                rows.append(more_row())
            return rows

        def load() -> list[Row]:
            state["page"] = 0
            rows = load_page()
            return rows or [Row("   (no builds)", GREY)]

        def load_more():
            self.msg = "Loading..."
            self.draw()
            try:
                rows = load_page()
                view.rows = view.rows[:-1] + rows
                self.msg = ""
            except JenkinsError as exc:
                self.msg = f"Error: {exc}"
            return None

        view.load = load
        return view

    def build(self, job: str, name: str, number: int) -> ListView:
        path = f"{job}/{number}"

        def load() -> list[Row]:
            b = self.jk.json(path, tree=BUILD_TREE)
            res = builds.result_of(b)
            rows = [
                Row(f"Result    {RESULT_SYMBOLS.get(res, '')} {res}", RESULT_PAIRS.get(res, 0), bold=True),
                Row(f"Started   {builds.started(b)}   by {builds.started_by(b)}"),
                Row(f"Duration  {builds.duration(b)}"),
                Row(f"URL       {self.base_url.rstrip('/')}{path}/", GREY),
            ]
            if b.get("description"):
                rows.append(Row(f"Note      {b['description']}"))
            rows += [Row(""), Row("STAGES", bold=True)]
            try:
                stages = json.loads(self.jk.text(f"{path}/wfapi/describe")).get("stages") or []
                for s in stages:
                    st = s.get("status", "")
                    secs = int((s.get("durationMillis") or 0) // 1000)
                    rows.append(Row(f"  {RESULT_SYMBOLS.get(st, ' ')} {s.get('name', ''):<50} {st:<12} "
                                    f"{secs // 60}m{secs % 60:02d}s", RESULT_PAIRS.get(st, 0)))
                if not stages:
                    rows.append(Row("  (no stages)", GREY))
            except (JenkinsError, ValueError):
                rows.append(Row("  (no stage data - not a pipeline, or the stage view plugin is missing)", GREY))
            rows += [Row(""), Row("PARAMETERS", bold=True)]
            params = [p for a in b.get("actions") or [] for p in (a or {}).get("parameters") or []]
            for p in params:
                v = p.get("value")
                empty = v in (None, "")
                parts = ["(empty)"] if empty else wrap(str(v))
                rows.append(Row(f"  {p['name']:<30} = {parts[0]}", YELLOW if empty else 0))
                rows += [Row(f"  {'':<30}   {part}") for part in parts[1:]]
            if not params:
                rows.append(Row("  (none)", GREY))
            return rows

        view = TextView(f"{name} #{number}", load, extra_keys="l log  j Jenkinsfile  f fetch to disk")
        view.build_ref = (job, name, number)
        return view

    def text_page(self, title: str, get_text, colorize: bool) -> TextView:
        def load() -> list[Row]:
            text = get_text()
            rows = []
            for line in text.splitlines():
                pair = 0
                if colorize:
                    if LOG_STAGE.search(line):
                        pair = CYAN
                    elif LOG_ERROR.search(line):
                        pair = RED
                rows.append(Row(line.replace("\t", "    "), pair))
            return rows or [Row("(empty)", GREY)]
        return TextView(title, load)

    def fetch_to_disk(self, job: str, number: int) -> None:
        out = self.out_dir / fetch.dir_name(job, number)
        if out.exists() and any(out.iterdir()):
            self.msg = f"Already saved (use jenkins fetch -f to overwrite): {out}"
            return
        lines: list[str] = []
        self.msg = "Fetching..."
        self.draw()
        try:
            fetch.save_build(self.jk, self.base_url, job, number, out, log=lines.append)
        except (JenkinsError, OSError) as exc:
            lines.append(f"ERROR: {exc}")
        view = TextView(f"fetched #{number}", lambda: [Row(l, RED if l.startswith(("ERROR", "  WARN")) else 0)
                                                      for l in lines])
        self.push(view)
        self.msg = f"Saved to {out}/"

    def start(self, path: str, title: str) -> ListView:
        """First screen: root, a folder, a job, or a build, depending on the URL given."""
        job, number = fetch.split_url(path)
        names = re.findall(r"/job/([^/]+)", job)
        name = unquote(names[-1]) if names else "/"
        if number is not None:
            return self.build(job, name, number)
        if path in ("", "/"):
            return self.folder("/", "/")
        try:
            kind = self.jk.json(path, tree="_class").get("_class", "")
        except JenkinsError as exc:
            self.msg = f"Error: {exc}"
            return self.folder("/", "/")
        return self.folder(path, title) if is_folder({"_class": kind}) else self.job(path, name)

    # drawing ------------------------------------------------------------

    def put(self, y: int, x: int, text: str, attr: int = 0) -> None:
        h, w = self.scr.getmaxyx()
        if 0 <= y < h and x < w:
            try:
                self.scr.addnstr(y, x, text, w - x - (1 if y == h - 1 else 0), attr)
            except curses.error:
                pass

    def draw(self) -> None:
        scr = self.scr
        scr.erase()
        h, w = scr.getmaxyx()
        view = self.stack[-1] if self.stack else None
        head = curses.color_pair(HEAD) | curses.A_BOLD
        self.put(0, 0, f" {self.header}".ljust(w), head)
        if view is None:
            self.put(2, 2, self.msg)
            scr.refresh()
            return
        crumbs = "  ›  ".join(v.title for v in self.stack[-3:])
        self.put(1, 0, f" {crumbs}"[:w], curses.A_BOLD)
        rows = view.visible()
        body = h - 4
        if view.selectable():
            view.sel = max(0, min(view.sel, len(rows) - 1))
            if view.sel < view.top:
                view.top = view.sel
            elif view.sel >= view.top + body:
                view.top = view.sel - body + 1
        view.top = max(0, min(view.top, max(0, len(rows) - body)))
        for i, row in enumerate(rows[view.top:view.top + body]):
            idx = view.top + i
            attr = curses.color_pair(row.pair) if row.pair else 0
            if row.bold:
                attr |= curses.A_BOLD
            if view.selectable() and idx == view.sel:
                attr |= curses.A_REVERSE
            text = f" {row.text}"
            if isinstance(view, TextView) and view.search and view.search.lower() in row.text.lower():
                attr = curses.color_pair(MATCH) | curses.A_BOLD
            self.put(2 + i, 0, text.ljust(w) if view.selectable() and idx == view.sel else text, attr)
        pos = f"{min(view.sel if view.selectable() else view.top, max(0, len(rows) - 1)) + 1}/{len(rows)}"
        flt = f"  filter: {view.filter}" if view.filter else ""
        self.put(h - 2, 0, f" {pos}{flt}   GET requests: {self.jk.requests}   {self.msg}"[:w],
                 curses.color_pair(GREY))
        self.put(h - 1, 0, f" {view.keys}"[:w], curses.color_pair(GREY) | curses.A_BOLD)
        scr.refresh()

    def prompt(self, label: str) -> str | None:
        h, w = self.scr.getmaxyx()
        text = ""
        curses.curs_set(1)
        try:
            while True:
                self.put(h - 1, 0, f" {label}{text}".ljust(w - 1), curses.A_BOLD)
                self.scr.move(h - 1, min(w - 2, len(label) + len(text) + 1))
                k = self.scr.getch()
                if k in (10, 13, curses.KEY_ENTER):
                    return text
                if k == 27:
                    return None
                if k in (curses.KEY_BACKSPACE, 127, 8):
                    text = text[:-1]
                elif 32 <= k < 127:
                    text += chr(k)
        finally:
            curses.curs_set(0)

    # keys ---------------------------------------------------------------

    def find(self, view: TextView, forward: bool = True) -> None:
        if not view.search:
            return
        rows, s = view.rows, view.search.lower()
        n = len(rows)
        for step in range(1, n + 1):
            i = (view.top + step) % n if forward else (view.top - step) % n
            if s in rows[i].text.lower():
                view.top = max(0, i - 3)
                self.msg = f"match at line {i + 1}"
                return
        self.msg = f"not found: {view.search}"

    def run(self, first: ListView) -> None:
        self.push(first)
        if not self.stack:
            self.stack.append(TextView("error", lambda: []))
            self.stack[-1].rows = [Row(self.msg, RED), Row(""), Row("press q to quit", GREY)]
        while self.stack:
            self.draw()
            k = self.scr.getch()
            view = self.stack[-1]
            rows = view.visible()
            h = self.scr.getmaxyx()[0]
            body = max(1, h - 4)
            if k in (ord("q"), ord("Q")):
                return
            if k == curses.KEY_RESIZE:
                continue
            if k in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 127, 8, ord("h")) or (k == 27 and not view.filter):
                if len(self.stack) > 1:
                    self.stack.pop()
                    self.msg = ""
                continue
            if k == 27:
                view.filter = ""
                continue
            if k == ord("r"):
                self.fill(view)
                continue
            if k == ord("/"):
                text = self.prompt("search: " if isinstance(view, TextView) else "filter: ")
                if text is not None:
                    if isinstance(view, TextView):
                        view.search = text
                        self.find(view)
                    else:
                        view.filter, view.sel, view.top = text, 0, 0
                continue
            if isinstance(view, TextView):
                self.text_keys(view, k, body)
                continue
            if k in (curses.KEY_UP, ord("k")):
                view.sel -= 1
            elif k in (curses.KEY_DOWN, ord("j")):
                view.sel += 1
            elif k == curses.KEY_PPAGE:
                view.sel -= body
            elif k == curses.KEY_NPAGE:
                view.sel += body
            elif k in (curses.KEY_HOME, ord("g")):
                view.sel = 0
            elif k in (curses.KEY_END, ord("G")):
                view.sel = len(rows) - 1
            elif k in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT, ord("l")) and rows:
                row = rows[max(0, min(view.sel, len(rows) - 1))]
                if row.open:
                    nxt = row.open()
                    if nxt is not None:
                        self.push(nxt)

    def text_keys(self, view: TextView, k: int, body: int) -> None:
        if k in (curses.KEY_UP, ord("k")):
            view.top -= 1
        elif k == curses.KEY_DOWN:
            view.top += 1
        elif k in (curses.KEY_PPAGE, ord("b")):
            view.top -= body
        elif k in (curses.KEY_NPAGE, ord(" ")):
            view.top += body
        elif k in (curses.KEY_HOME, ord("g")):
            view.top = 0
        elif k in (curses.KEY_END, ord("G")):
            view.top = len(view.rows)
        elif k == ord("n"):
            self.find(view, True)
        elif k == ord("N"):
            self.find(view, False)
        elif k in (ord("l"), ord("j"), ord("f")) and getattr(view, "build_ref", None):
            job, name, number = view.build_ref
            path = f"{job}/{number}"
            if k == ord("l"):
                self.push(self.text_page(f"log #{number}", lambda: self.jk.text(f"{path}/consoleText"), True))
                if self.stack[-1].title == f"log #{number}":
                    self.stack[-1].top = max(0, len(self.stack[-1].rows) - body)
                    self.msg = "showing the end of the log (g = top)"
            elif k == ord("j"):
                def jf():
                    t = fetch.jenkinsfile_text(self.jk, path)
                    if t is None:
                        raise JenkinsError("no Jenkinsfile on the replay page (permissions, or not a pipeline)")
                    return t
                self.push(self.text_page(f"Jenkinsfile #{number}", jf, False))
            elif k == ord("f"):
                self.fetch_to_disk(job, number)


def run(jk: Jenkins, base_url: str, header: str, out_dir: Path, start_path: str = "/", start_title: str = "/") -> None:
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")  # Esc reacts at once instead of after 1 s

    def main(scr):
        curses.curs_set(0)
        curses.use_default_colors()
        for pair, fg in ((GREEN, curses.COLOR_GREEN), (RED, curses.COLOR_RED), (YELLOW, curses.COLOR_YELLOW),
                         (GREY, 8 if curses.COLORS > 8 else curses.COLOR_WHITE), (CYAN, curses.COLOR_CYAN)):
            curses.init_pair(pair, fg, -1)
        curses.init_pair(HEAD, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.init_pair(MATCH, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        app = App(scr, jk, base_url, header, out_dir)
        app.run(app.start(start_path, start_title))

    curses.wrapper(main)
