"""Open a local port that reaches Jenkins.

Two ways, chosen from the config:
  1. tunnels CLI  - when installed and tunnel.tunnels_target is set.
                    The tunnel is left up afterwards (tunnels manages it).
  2. plain SSM    - `aws ssm start-session` port forward, opened for this
                    command only and closed when it finishes.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from . import awslogin

TUNNELS_STATE = Path.home() / ".tunnels" / "state.json"


class ConnectError(Exception):
    pass


def method(inst: dict) -> str:
    tunnel = inst.get("tunnel") or {}
    if tunnel.get("tunnels_target") and shutil.which("tunnels"):
        return "tunnels"
    if tunnel.get("ssm"):
        return "ssm"
    if tunnel.get("tunnels_target"):
        raise ConnectError("tunnel.tunnels_target is set but the 'tunnels' CLI is not installed, "
                           "and there is no tunnel.ssm fallback in the config")
    raise ConnectError("no tunnel settings in the config (tunnel.tunnels_target or tunnel.ssm)")


@contextmanager
def open_port(inst: dict):
    """Yield (local port forwarded to Jenkins, method actually used).

    tunnels is tried first when configured; if it is not installed or cannot
    bring the tunnel up, the plain SSM block is used instead.
    """
    how = method(inst)
    if how == "tunnels":
        try:
            port = _tunnels_port(inst["tunnel"]["tunnels_target"])
        except ConnectError as exc:
            if not inst["tunnel"].get("ssm"):
                raise
            print(f"WARNING: tunnels failed: {exc}\n         Falling back to plain SSM.", file=sys.stderr)
        else:
            yield port, "tunnels"
            return
    elif inst["tunnel"].get("tunnels_target"):
        print("NOTE: tunnels_target is set but the 'tunnels' CLI is not installed - using plain SSM.",
              file=sys.stderr)
    with _ssm_port(inst) as port:
        yield port, "ssm"


# ─── tunnels CLI ────────────────────────────────────────────────────────────

def _read_tunnels_port(env: str, target: str) -> int | None:
    try:
        entries = json.loads(TUNNELS_STATE.read_text())
    except (OSError, ValueError):
        return None
    for entry in entries if isinstance(entries, list) else []:
        if entry.get("config") == env and entry.get("target") == target:
            return entry.get("local_port")
    return None


def _tunnels_port(spec: str) -> int:
    env, sep, target = spec.partition("/")
    if not sep or not target:
        raise ConnectError(f"tunnels_target must look like '<env>/<target>', got '{spec}'")
    port = _read_tunnels_port(env, target)
    if port and _port_open(port):
        return port
    print(f"Starting tunnel via tunnels: {env}/{target} ...", file=sys.stderr)
    # tunnels writes its own progress; send it to stderr so stdout stays clean
    rc = subprocess.run(["tunnels", "up", env, target], stdout=sys.stderr).returncode
    port = _read_tunnels_port(env, target)
    if not port or not _wait_port(port, 20):
        raise ConnectError(f"'tunnels up {env} {target}' did not bring the tunnel up (exit {rc}). "
                           f"See: tunnels logs {env} {target}")
    return port


# ─── plain SSM ──────────────────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _wait_port(port: int, seconds: int) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _port_open(port):
            return True
        time.sleep(0.5)
    return False


@contextmanager
def _ssm_port(inst: dict):
    ssm = inst["tunnel"]["ssm"]
    if not shutil.which("aws"):
        raise ConnectError("the AWS CLI is not installed")
    if not shutil.which("session-manager-plugin"):
        raise ConnectError("the AWS Session Manager plugin is not installed "
                           "(brew install --cask session-manager-plugin)")

    profile, region = ssm["profile"], ssm["region"]
    awslogin.ensure_login(profile)

    remote_host = ssm.get("remote_host") or urlparse(inst["url"]).hostname
    remote_port = int(ssm.get("remote_port") or 443)
    wanted = ssm.get("local_port", "auto")
    port = _free_port() if wanted in (None, "auto") else int(wanted)
    if wanted not in (None, "auto") and _port_open(port):
        raise ConnectError(f"local port {port} is already in use - set tunnel.ssm.local_port: auto")

    params = json.dumps({"host": [remote_host], "portNumber": [str(remote_port)],
                         "localPortNumber": [str(port)]})
    print(f"Starting SSM tunnel 127.0.0.1:{port} -> {remote_host}:{remote_port} ...", file=sys.stderr)
    proc = subprocess.Popen(
        ["aws", "ssm", "start-session", "--profile", profile, "--region", region,
         "--target", ssm["instance"],
         "--document-name", "AWS-StartPortForwardingSessionToRemoteHost",
         "--parameters", params],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        start_new_session=True,  # own process group, so the plugin child is stopped too
    )
    try:
        if not _wait_port(port, 30) or proc.poll() is not None:
            err = proc.stderr.read().decode(errors="replace").strip() if proc.poll() is not None else ""
            raise ConnectError(f"SSM tunnel did not come up within 30s. {err}".strip())
        yield port
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
