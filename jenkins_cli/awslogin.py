"""Make sure an AWS profile has a valid session, running `aws sso login` if needed.

The browser approval cannot be automated (it is an OAuth device grant). This
only starts it at the right moment. No token is read or stored here.
"""

from __future__ import annotations

import configparser
import os
import subprocess
import sys
from pathlib import Path

AWS_CONFIG = Path(os.environ.get("AWS_CONFIG_FILE") or Path.home() / ".aws" / "config")


class AwsError(Exception):
    pass


def profiles() -> list[str]:
    cp = configparser.RawConfigParser()
    cp.read(AWS_CONFIG)
    names = []
    for section in cp.sections():
        if section.startswith("profile "):
            names.append(section[len("profile "):].strip())
        elif section == "default":
            names.append("default")
    return names


def _is_sso(profile: str) -> bool:
    cp = configparser.RawConfigParser()
    cp.read(AWS_CONFIG)
    section = "default" if profile == "default" else f"profile {profile}"
    if not cp.has_section(section):
        return False
    return cp.has_option(section, "sso_session") or cp.has_option(section, "sso_start_url")


def logged_in(profile: str) -> bool:
    return subprocess.run(
        ["aws", "sts", "get-caller-identity", "--profile", profile],
        capture_output=True,
    ).returncode == 0


def ensure_login(profile: str) -> None:
    if logged_in(profile):
        return
    if not _is_sso(profile):
        raise AwsError(f"AWS profile '{profile}' has no valid credentials (and is not an SSO profile)")
    print(f"AWS session for '{profile}' expired - starting 'aws sso login' (approve it in the browser)...",
          file=sys.stderr)
    if subprocess.run(["aws", "sso", "login", "--profile", profile]).returncode != 0:
        raise AwsError(f"aws sso login failed for profile '{profile}'")
    if not logged_in(profile):
        raise AwsError(f"still no valid AWS session for '{profile}' after login")
