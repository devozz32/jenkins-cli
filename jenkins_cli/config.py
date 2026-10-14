"""Load and save ~/.jenkins-cli/config.yaml.

Every company-specific value (URLs, AWS profile, instance IDs, users) lives in
this file. The code only knows the shape of it.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import yaml

CONFIG_PATH = Path(os.environ.get("JENKINS_CLI_CONFIG") or Path.home() / ".jenkins-cli" / "config.yaml")
DEFAULT_OUTPUT_DIR = "~/jenkins-investigations"


class ConfigError(Exception):
    pass


def load(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        raise ConfigError(f"no config file at {path} - run: jenkins init")
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if not data.get("instances"):
        raise ConfigError(f"{path} has no 'instances' - run: jenkins init")
    return data


def load_or_empty(path: Path = CONFIG_PATH) -> dict:
    try:
        return load(path)
    except ConfigError:
        return {"instances": {}}


def save(data: dict, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    path.chmod(0o600)


def output_dir(data: dict) -> Path:
    return Path(os.path.expanduser(data.get("output_dir") or DEFAULT_OUTPUT_DIR))


def instance(data: dict, name: str | None = None, url: str | None = None) -> tuple[str, dict]:
    """Pick an instance: explicit name > one whose host matches url > default."""
    instances = data["instances"]
    if name:
        if name not in instances:
            raise ConfigError(f"unknown instance '{name}'. Known: {', '.join(instances)}")
        return name, instances[name]
    if url:
        host = urlparse(url).hostname
        for key, inst in instances.items():
            if urlparse(inst.get("url", "")).hostname == host:
                return key, inst
    default = data.get("default") or next(iter(instances))
    if default not in instances:
        raise ConfigError(f"default instance '{default}' is not defined under instances")
    return default, instances[default]


def validate_instance(name: str, inst: dict) -> None:
    missing = [k for k in ("url", "user", "token") if not inst.get(k)]
    if missing:
        raise ConfigError(f"instance '{name}' is missing: {', '.join(missing)} (in {CONFIG_PATH})")
    tunnel = inst.get("tunnel") or {}
    if not tunnel.get("tunnels_target") and not tunnel.get("ssm"):
        raise ConfigError(
            f"instance '{name}' has no tunnel settings - set tunnel.tunnels_target or tunnel.ssm in {CONFIG_PATH}"
        )
    ssm = tunnel.get("ssm")
    if ssm:
        missing = [k for k in ("profile", "region", "instance") if not ssm.get(k)]
        if missing:
            raise ConfigError(f"instance '{name}' tunnel.ssm is missing: {', '.join(missing)}")
