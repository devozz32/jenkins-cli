"""Minimal Jenkins REST client over a local forwarded port."""

from __future__ import annotations

import base64
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class JenkinsError(Exception):
    pass


class Jenkins:
    def __init__(self, port: int, user: str, token: str):
        self.base = f"https://127.0.0.1:{port}"
        self._auth = "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()
        # The tunnel ends on 127.0.0.1, so the certificate name cannot match (same as curl -k today).
        self._ssl = ssl.create_default_context()
        self._ssl.check_hostname = False
        self._ssl.verify_mode = ssl.CERT_NONE

    @staticmethod
    def path_of(url: str) -> str:
        """'https://jenkins.x/job/A/12/' -> '/job/A/12' (keeps %-encoding as given)."""
        return urlparse(url).path.rstrip("/") if "://" in url else url.rstrip("/")

    def _open(self, path: str, params: dict | None = None, timeout: int = 60):
        url = self.base + path
        if params:
            url += "?" + urlencode(params)  # encodes [ ] { } properly
        req = Request(url, headers={"Authorization": self._auth})
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
