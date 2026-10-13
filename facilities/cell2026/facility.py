"""Shinobu Lab cell2026 registration for the unified hub."""
import os
import re
from pathlib import Path

from hpc_agent_core import config
from hpc_agent_core.models import JobSpec
from facilities.cell2026.compute import Cell2026Backend
from facilities.registry import register_backend

SLUG = "cell2026"

FACILITY = config.register_facility(
    slug=SLUG,
    display_name="cell2026 (Shinobu Lab)",
    description="Dual-scheduler GPU cluster: Grid Engine on helix/kinase "
                "with managed RTX A4000 GPUs and durable qacct, plus "
                "no-accounting Slurm on beta/serine with unmanaged GPUs.",
    default_host="cell2026",
    data_dir=Path(__file__).parent / "data",
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",
    embed_model="bge-m3:567m",
    docs_cite_url="",
    config_example={"ssh": {"host": "cell2026"}},
    setup_help=(
        "cell2026 requires non-interactive key-based SSH. Add a\n"
        "'cell2026' alias to ~/.ssh/config using the hostname and username\n"
        "issued by the lab, or set ssh.host to that user@host. There is no\n"
        "public login hostname to guess. Use host=localhost when the agent\n"
        "already runs on the head node. No project/account is configured:\n"
        "neither scheduler uses one. CELL2026_DEFAULT_SCHEDULER may be\n"
        "'gridengine' (the default) or 'slurm'; CELL2026_GE_BIN can name\n"
        "the AGE binary directory if the login shell does not put it on PATH."
    ),
)


def _default_scheduler() -> str:
    value = os.environ.get("CELL2026_DEFAULT_SCHEDULER", "gridengine").lower()
    if value not in {"gridengine", "slurm"}:
        raise ValueError(
            "CELL2026_DEFAULT_SCHEDULER must be 'gridengine' or 'slurm'; "
            f"got {value!r}."
        )
    return value


def _ge_bin_prefix() -> str:
    value = os.environ.get("CELL2026_GE_BIN", "")
    if value and not re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        # Never let a malformed optional env var deny every other facility
        # server startup. Ignore it safely; doctor will then report that the
        # AGE commands are unavailable on PATH.
        return ""
    return value


class ConfiguredCell2026Backend(Cell2026Backend):
    def apply_defaults(self, spec: JobSpec) -> None:
        if not spec.attributes.queue_name:
            scheduler = (
                spec.attributes.scheduler.value
                if spec.attributes.scheduler is not None
                else _default_scheduler()
            )
            spec.attributes.queue_name = "all" if scheduler == "slurm" else "all.q"


BACKEND = ConfiguredCell2026Backend(
    facility=SLUG,
    ge_bin_prefix=_ge_bin_prefix(),
)
register_backend(SLUG, BACKEND)
