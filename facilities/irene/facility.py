"""CEA TGCC Irene registration for the unified hub.

The separate IreneAgent migration passed offline behavioral-equivalence tests,
but neither that migration nor this hub port had live TGCC access.  Keep Irene
in the awaiting-validation group until doctor, live status, and a tiny Bridge
job have all been exercised again.
"""
import os
from pathlib import Path

from hpc_agent_core import config
from hpc_agent_core.models import JobSpec
from facilities.irene.compute import BridgeBackend
from facilities.registry import register_backend

SLUG = "irene"

FACILITY = config.register_facility(
    slug=SLUG,
    display_name="Irene (CEA TGCC)",
    description="CEA TGCC Irene: CPU-first AMD Rome system with specialized "
                "large-memory and NVIDIA GPU partitions, using Bridge #MSUB "
                "directives and ccc_* commands.",
    default_host="irene",
    data_dir=Path(__file__).parent / "data",
    embed_base_url="",
    embed_model="",
    docs_cite_url="",
    config_example={
        "ssh": {"host": "irene"},
        "computer": {"passfile": "/path/to/local/password-file-if-needed"},
        "defaults": {
            "account": "<your-TGCC-project>",
            "filesystems": "scratch,work",
        },
    },
    setup_help=(
        "Use the Irene SSH destination issued in your TGCC project\n"
        "documentation; no public hostname is assumed here. Prefer an\n"
        "existing 'irene' alias in ~/.ssh/config, or set ssh.host to the\n"
        "issued user@host. If the account needs password-file authentication,\n"
        "put that local path under computer.passfile (not ssh.passfile).\n"
        "Set defaults.account only to a project returned by get_projects;\n"
        "Bridge checks that project against the requested partition before\n"
        "submitting. defaults.filesystems supplies mandatory #MSUB -m and\n"
        "normally starts as scratch,work. IRENE_ACCOUNT and\n"
        "IRENE_FILESYSTEMS override those values. Use host=localhost when\n"
        "already running on an Irene front end."
    ),
)


def _default_account() -> str | None:
    cfg = config.file_config(SLUG)
    return (os.environ.get("IRENE_ACCOUNT")
            or (cfg.get("defaults") or {}).get("account")
            or cfg.get("account")
            or None)


def _default_filesystems() -> str:
    cfg = config.file_config(SLUG)
    return (os.environ.get("IRENE_FILESYSTEMS")
            or (cfg.get("defaults") or {}).get("filesystems")
            or cfg.get("filesystems")
            or "scratch,work")


class IreneBackend(BridgeBackend):
    def apply_defaults(self, spec: JobSpec) -> None:
        if not spec.attributes.queue_name:
            spec.attributes.queue_name = "rome"
        if spec.attributes.account is None:
            spec.attributes.account = _default_account()
        if not spec.attributes.account:
            raise ValueError(
                "Irene requires a TGCC project for #MSUB -A. Set "
                "spec.attributes.account, or configure defaults.account in "
                f"{config.config_path(SLUG)} (or IRENE_ACCOUNT). Use "
                "get_projects after connecting to list the current user's "
                "real project/partition associations; never copy an example."
            )
        custom = spec.attributes.custom_attributes
        if "filesystems" not in custom and "m" not in custom:
            custom["filesystems"] = _default_filesystems()


BACKEND = IreneBackend(facility=SLUG)
register_backend(SLUG, BACKEND)
