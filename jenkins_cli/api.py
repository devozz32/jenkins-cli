"""Minimal Jenkins REST client over a local forwarded port."""

from __future__ import annotations

import base64
import json
import re
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class JenkinsError(Exception):
    pass


# Read-only lock. This client only ever sends GET requests without a body, and
# refuses any URL whose path names a Jenkins action that changes something,
# even if Jenkins would accept it as GET. Checked before anything is sent.
_WRITE_ACTIONS = re.compile(
    r"(?<!/job)(?<!/view)/(build|buildWithParameters|polling|rebuild|stop|term|kill|doDelete|doWipeOutWorkspace"
    r"|delete|deleteBuild|configSubmit|submitDescription|toggleLogKeep|disable|enable|doRename"
    r"|confirmRename|createItem|copy|doReload|reload|restart|safeRestart|exit|safeExit|quietDown"
    r"|cancelQuietDown|scriptText|script|cli|input|proceed|abort|run|rebuildAll|doCreateItem"
    r"|updateNode|toggleOffline|disconnect|launchSlaveAgent|cancelItem)(/|$)",
    re.IGNORECASE,
)
_MIN_GAP = 0.2  # seconds between requests: at most ~5 per second, never a flood


def check_read_only(path: str) -> None:
    """Raise JenkinsError if `path` (without query) names a write action."""
    m = _WRITE_ACTIONS.search(urlparse(path).path)
    if m:
        raise JenkinsError(f"refused: '{m.group(1)}' changes Jenkins and this CLI is read-only ({path})")


class Jenkins:
    def __init__(self, port: int, user: str, token: str):
        self.base = f"https://127.0.0.1:{port}"
        self._auth = "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()
        # The tunnel ends on 127.0.0.1, so the certificate name cannot match (same as curl -k today).
        self._ssl = ssl.create_default_context()
        self._ssl.check_hostname = False
        self._ssl.verify_mode = ssl.CERT_NONE
        self._last = 0.0
        self.requests = 0  # GETs sent, shown by `jenkins browse`

    @staticmethod
    def path_of(url: str) -> str:
        """'https://jenkins.x/job/A/12/' -> '/job/A/12' (keeps %-encoding as given)."""
        return urlparse(url).path.rstrip("/") if "://" in url else url.rstrip("/")

    def _open(self, path: str, params: dict | None = None, timeout: int = 60):
        check_read_only(path)
        url = self.base + path
        if params:
            url += "?" + urlencode(params)  # encodes [ ] { } properly
        req = Request(url, headers={"Authorization": self._auth}, method="GET")
        wait = self._last + _MIN_GAP - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.requests += 1
        try:
            return urlopen(req, context=self._ssl, timeout=timeout)
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise JenkinsError(f"HTTP {exc.code} on {path} - check user/token or permissions") from exc
            if exc.code == 404:
                raise JenkinsError(f"not found: {path}") from exc
            raise JenkinsError(f"HTTP {exc.code} on {path}") from exc
        except URLError as exc:
            raise JenkinsError(f"cannot reach Jenkins through the tunnel: {exc.reason}") from exc

    def text(self, path: str, params: dict | None = None) -> str:
        with self._open(path, params) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def json(self, path: str, tree: str | None = None) -> dict:
        body = self.text(path.rstrip("/") + "/api/json", {"tree": tree} if tree else None)
        try:
            return json.loads(body)
        except ValueError as exc:
            raise JenkinsError(f"{path}/api/json did not return JSON (first 200 chars): {body[:200]}") from exc

    def download(self, path: str, dest, chunk: int = 1 << 16) -> int:
        size = 0
        with self._open(path, timeout=300) as resp, open(dest, "wb") as fh:
            while True:
                data = resp.read(chunk)
                if not data:
                    break
                fh.write(data)
                size += len(data)
        return size

    def whoami(self) -> dict:
        return self.json("/whoAmI", tree="name,authenticated")
