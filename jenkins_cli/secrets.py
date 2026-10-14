"""Jenkins API token storage.

The config never holds the token itself, only a reference:
  keychain:<name>   macOS Keychain item (service "jenkins-cli", account <name>)
  env:<VAR>         environment variable
"""

from __future__ import annotations

import os
import subprocess

SERVICE = "jenkins-cli"


class SecretError(Exception):
    pass


def resolve(ref: str) -> str:
    kind, _, name = ref.partition(":")
    if kind == "keychain" and name:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
            capture_output=True, text=True,
        )
        if out.returncode != 0:
            raise SecretError(f"no Keychain item for '{name}' - run: jenkins init")
        return out.stdout.strip()
    if kind == "env" and name:
        value = os.environ.get(name)
        if not value:
            raise SecretError(f"environment variable {name} is not set")
        return value
    raise SecretError(f"token must be 'keychain:<name>' or 'env:<VAR>', got '{ref}'")


def store_keychain(name: str) -> None:
    """Let `security` prompt for the token itself, so it never appears in argv."""
    print(f"Paste the Jenkins API token (stored in macOS Keychain as {SERVICE}/{name}).")
    rc = subprocess.run(
        ["security", "add-generic-password", "-s", SERVICE, "-a", name, "-U", "-w"]
    ).returncode
    if rc != 0:
        raise SecretError("could not save the token to the Keychain")
