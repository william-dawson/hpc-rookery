"""Science Tokyo TSUBAME4 registration for the unified hub.

This port is based on the separate Tsubame4-Agent implementation and its
offline migration checks.  The hub port has not been exercised against the
live machine, so scheduler commands and parsers remain explicitly awaiting
live validation.
"""
import os
from pathlib import Path

from hpc_agent_core import config
from hpc_agent_core.models import JobSpec
from facilities.registry import register_backend
from facilities.tsubame.compute import TsubameBackend

SLUG = "tsubame"

FACILITY = config.register_facility(
    slug=SLUG,
    display_name="TSUBAME4.0 (Science Tokyo)",
    description="Science Tokyo TSUBAME4: 240 H100 GPU nodes, Altair Grid "
                "Engine, fixed resource-type slices, and group point billing.",
    default_host="tsubame",
    data_dir=Path(__file__).parent / "data",
    embed_base_url="",
    embed_model="",
    docs_cite_url="https://www.t4.cii.isct.ac.jp/en/",
    config_example={
        "ssh": {"host": "tsubame"},
        "defaults": {"group": "<your-TSUBAME-group>"},
    },
    setup_help=(
        "TSUBAME4 accepts registered SSH keys, not password prompts. Register\n"
        "your public key in the TSUBAME portal, then add a 'tsubame' alias\n"
        "to ~/.ssh/config pointing at login.t4.gsic.titech.ac.jp and your\n"
        "Science Tokyo username, or set ssh.host to that user@host value.\n"
        "Set defaults.group to a TSUBAME group returned by get_projects if\n"
        "normal jobs should charge it. Omitting the group deliberately uses\n"
        "the free trial limits (2 resource units, 3 minutes, priority -5).\n"
        "Never copy a group name from an example. TSUBAME_GROUP overrides\n"
        "the configured default; use host=localhost when already logged in."
    ),
)


def _default_group() -> str | None:
    """TSUBAME_GROUP > defaults.group > legacy group; no bundled account."""
    cfg = config.file_config(SLUG)
    return (os.environ.get(f"{FACILITY.env_prefix}_GROUP")
            or (cfg.get("defaults") or {}).get("group")
            or cfg.get("group")
            or None)


class ConfiguredTsubameBackend(TsubameBackend):
    def apply_defaults(self, spec: JobSpec) -> None:
        if spec.attributes.account is None:
            spec.attributes.account = _default_group()
        spec.attributes.custom_attributes.setdefault("resource_type", "node_f")
        spec.attributes.custom_attributes.setdefault("priority", "-5")


BACKEND = ConfiguredTsubameBackend(facility=SLUG)
register_backend(SLUG, BACKEND)
