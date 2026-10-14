"""jenkins-cli: fetch and inspect Jenkins builds through AWS SSM port forwarding."""

try:
    from importlib.metadata import version as _version

    __version__ = _version("jenkins-cli")
except Exception:  # running from a checkout without installing
    __version__ = "0.0.0+local"
