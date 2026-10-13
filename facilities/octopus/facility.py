"""RIKEN Octopus registration for the unified hub.

The separate Octopus-Agent was migrated to hpc-agent-core and checked
offline, but neither that migration nor this hub port had live Octopus SSH
access.  Its Slurm dialect is straightforward; the important local behavior
is the partition-selected GPU vendor and the machine's small, fixed resource
envelope.
"""
import os
from pathlib import Path

from hpc_agent_core import config
from hpc_agent_core.compute.slurm import SlurmBackend
from hpc_agent_core.models import JobSpec
from facilities.registry import register_backend

SLUG = "octopus"
_PARTITIONS = frozenset({"h200", "h200-long", "mi300x", "mi300x-long"})
_SHORT_PARTITIONS = frozenset({"h200", "mi300x"})
_MAX_MEMORY_BYTES = 2_317_610 * 1024**2

FACILITY = config.register_facility(
    slug=SLUG,
    display_name="Octopus (RIKEN R-CCS)",
    description="RIKEN R-CCS dual-vendor GPU cluster: three NVIDIA H200 "
                "nodes and one AMD MI300X node, Slurm with accounting, "
                "untyped per-node GRES requests.",
    default_host="octopus",
    data_dir=Path(__file__).parent / "data",
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",
    embed_model="bge-m3:567m",
    docs_cite_url="",
    config_example={"ssh": {"host": "octopus"}},
    setup_help=(
        "Octopus accepts non-interactive, key-based SSH; the MCP server cannot\n"
        "answer a password prompt. Add an 'octopus' alias to ~/.ssh/config\n"
        "using the management-node hostname and username issued to you by\n"
        "the site, or set ssh.host to that user@host value directly.\n"
        "No account is normally required in the config: Slurm applies the\n"
        "user's DefaultAccount. If you belong to several projects and want\n"
        "a persistent override, add defaults.account after get_projects has\n"
        "shown the real account names; never copy another user's account.\n"
        "Running on an Octopus front end? Use host=localhost instead."
    ),
)


def _default_account() -> str | None:
    """Optional account override; Slurm's DefaultAccount is the fallback."""
    cfg = config.file_config(SLUG)
    return (os.environ.get(f"{FACILITY.env_prefix}_ACCOUNT")
            or (cfg.get("defaults") or {}).get("account")
            or cfg.get("account")
            or None)


def _duration_seconds(value: int | str) -> int:
    if isinstance(value, int):
        return value
    days = 0
    clock = value
    if "-" in value:
        day_text, clock = value.split("-", 1)
        days = int(day_text)
    hours, minutes, seconds = (int(part) for part in clock.split(":"))
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


class OctopusBackend(SlurmBackend):
    def apply_defaults(self, spec: JobSpec) -> None:
        """Default a partial request to one H200 GPU.

        An explicit account remains optional: Octopus configures a Slurm
        DefaultAccount for every user.
        """
        if not spec.attributes.queue_name:
            spec.attributes.queue_name = "h200"
        if not spec.resources.gpus and not spec.resources.gpu_cores_per_process:
            spec.resources.gpus = 1
        if spec.attributes.account is None:
            spec.attributes.account = _default_account()

    def validate_spec(self, spec: JobSpec) -> None:
        attrs, resources = spec.attributes, spec.resources
        queue = attrs.queue_name
        if queue not in _PARTITIONS:
            raise ValueError(
                f"Octopus has four GPU partitions: {sorted(_PARTITIONS)}. "
                f"Set spec.attributes.queue_name to one of them; got {queue!r}."
            )

        gpus = resources.gpus or resources.gpu_cores_per_process
        if not gpus:
            raise ValueError(
                "Every Octopus partition is GPU-backed. Set resources.gpus "
                "between 1 and 8, or leave it unset so apply_defaults uses 1."
            )
        if gpus > 8:
            raise ValueError(
                f"Octopus exposes at most 8 GPUs per node; got {gpus}. "
                "Reduce resources.gpus to a value from 1 through 8."
            )

        # The current bundled partition inventory records MaxNodes=1 for all
        # four partitions. This also avoids pretending ResourceSpec.gpus
        # (documented as a job-total count) is a per-node total on multi-node
        # --gres jobs. Refresh this rule live before widening it.
        if resources.node_count != 1:
            raise ValueError(
                "The recorded Octopus partition limits allow one node per "
                "job. Set resources.node_count=1; recheck the live Slurm "
                "configuration before enabling multi-node requests."
            )

        tasks = resources.processes_per_node
        if resources.process_count is not None:
            tasks = resources.process_count
        requested_cores = tasks * (resources.cpu_cores_per_process or 1)
        if requested_cores > 192:
            raise ValueError(
                f"An Octopus node has 192 CPU cores, but this shape requests "
                f"{requested_cores}. Reduce process_count/processes_per_node "
                "or cpu_cores_per_process."
            )
        if resources.memory and resources.memory > _MAX_MEMORY_BYTES:
            raise ValueError(
                "The recorded usable memory limit is 2,317,610 MiB per "
                "Octopus node. Reduce resources.memory."
            )
        if queue in _SHORT_PARTITIONS and _duration_seconds(attrs.duration) > 8 * 3600:
            vendor = "h200-long" if queue == "h200" else "mi300x-long"
            raise ValueError(
                f"Octopus partition {queue!r} has an 8-hour limit. Reduce "
                f"attributes.duration or use {vendor!r} for a genuinely "
                "longer job."
            )


BACKEND = OctopusBackend(
    facility=SLUG,
    has_accounting=True,
    gpu_request_style="gres",
    gpu_vendor_map={"h200": "--nv", "mi300x": "--rocm"},
)
register_backend(SLUG, BACKEND)
