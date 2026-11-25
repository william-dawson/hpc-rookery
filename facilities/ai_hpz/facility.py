"""ai-hpz (hpz workstation) registration for the unified hub.

hpz is a single Ubuntu 24.04 workstation running its own Slurm controller:
one node, one partition (``debug``), 24 logical CPUs, ~187 GiB of memory and
one Quadro RTX 5000. Facts below were read live from the machine
(``scontrol show config``/``show partition``/``show node``, ``nvidia-smi``,
and test jobs) on 2026-11-25.

Two properties shape this backend:

- **No accounting.** ``AccountingStorageType`` is unset, so status comes
  from squeue/scontrol and there is no sacct history or sacctmgr project
  list (``has_accounting=False``).
- **One GPU as a Slurm GRES.** ``GresTypes=gpu`` with
  ``Gres=gpu:quadro_rtx_5000:1`` (gres.conf ``AutoDetect=nvidia``).
  ``--gres=gpu:1`` reserves it: a second GPU job pends with reason
  ``Resources`` and the holder gets ``CUDA_VISIBLE_DEVICES=0``;
  ``--gres=gpu:2`` is refused at submit time. There is no cgroup.conf
  (no ``ConstrainDevices``), so a job that did *not* request the GPU can
  still see and use it — reservation is cooperative, not enforced.
"""
from pathlib import Path

from hpc_agent_core import config
from hpc_agent_core.compute.slurm import SlurmBackend
from hpc_agent_core.models import JobSpec
from facilities.registry import register_backend

SLUG = "ai-hpz"
_PARTITION = "debug"
_CPUS = 24                       # 12 cores x 2 hyperthreads, as Slurm counts them
_MAX_MEMORY_BYTES = 192_117 * 1024**2   # node RealMemory (MiB)

FACILITY = config.register_facility(
    slug=SLUG,
    display_name="ai-hpz (hpz workstation)",
    description="Single-node Ubuntu workstation with its own Slurm (one "
                "'debug' partition, 24 CPUs, ~187 GiB, no accounting) and one "
                "Quadro RTX 5000 requested as --gres=gpu:1; GROMACS 2026 "
                "(CUDA) and NVIDIA HPC SDK 24.5 installed.",
    default_host="ai-hpz",
    data_dir=Path(__file__).parent / "data",
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",
    embed_model="bge-m3:567m",
    docs_cite_url="",
    config_example={"ssh": {"host": "ai-hpz"}},
    setup_help=(
        "hpz needs non-interactive key-based SSH; the MCP server cannot\n"
        "answer a password prompt. Add an 'ai-hpz' Host alias to\n"
        "~/.ssh/config with the HostName, User and IdentityFile the machine's\n"
        "administrator gave you, and check that `ssh ai-hpz hostname` prints\n"
        "'hpz' without prompting. No project/account is needed: Slurm here\n"
        "has no accounting. Running on hpz itself? Use host=localhost."
    ),
)


class AiHpzBackend(SlurmBackend):
    _NO_ACCOUNTING = "Slurm on hpz runs without accounting, so there are no projects or allocations"

    def get_projects(self) -> list[dict]:
        raise self._unsupported("project listing", self._NO_ACCOUNTING)

    def get_project_allocations(self, project_id: str) -> dict:
        raise self._unsupported("project allocations", self._NO_ACCOUNTING)

    def get_user_allocations(self, project_id: str) -> dict:
        raise self._unsupported("user allocations", self._NO_ACCOUNTING)

    def apply_defaults(self, spec: JobSpec) -> None:
        """hpz has exactly one partition, so a blank queue means it."""
        if not spec.attributes.queue_name:
            spec.attributes.queue_name = _PARTITION

    def validate_spec(self, spec: JobSpec) -> None:
        attrs, resources = spec.attributes, spec.resources
        if attrs.queue_name != _PARTITION:
            raise ValueError(
                f"hpz has one Slurm partition, {_PARTITION!r}. Set "
                f"spec.attributes.queue_name to {_PARTITION!r} or leave it "
                f"blank; got {attrs.queue_name!r}."
            )
        if attrs.account:
            raise ValueError(
                "hpz's Slurm has no accounting, so there are no projects to "
                "bill. Leave spec.attributes.account unset."
            )
        if resources.node_count != 1:
            raise ValueError(
                "hpz is a single node. Set resources.node_count=1."
            )
        if resources.gpu_cores_per_process:
            raise ValueError(
                "gpu_cores_per_process is not mapped on hpz. Use "
                "resources.gpus (0 or 1) instead."
            )
        if resources.gpus and resources.gpus > 1:
            raise ValueError(
                f"hpz has one GPU (Quadro RTX 5000); got gpus={resources.gpus}. "
                "Set resources.gpus to 0 or 1; Slurm refuses gpu:2 at submit."
            )
        if spec.container is not None:
            raise ValueError(
                "hpz has no Singularity/Apptainer, which is what container "
                "jobs render to. Run the software installed on the host "
                "(e.g. GROMACS in /usr/local/gromacs) instead."
            )
        tasks = resources.processes_per_node
        if resources.process_count is not None:
            tasks = resources.process_count
        requested = tasks * (resources.cpu_cores_per_process or 1)
        if requested > _CPUS:
            raise ValueError(
                f"hpz has {_CPUS} CPUs (12 cores x 2 threads) but this shape "
                f"requests {requested}. Reduce process_count/"
                "processes_per_node or cpu_cores_per_process."
            )
        if resources.memory and resources.memory > _MAX_MEMORY_BYTES:
            raise ValueError(
                "hpz's Slurm node offers 192,117 MiB. Reduce resources.memory."
            )
        # MaxTime is UNLIMITED on debug, so duration needs no check here.


BACKEND = AiHpzBackend(
    facility=SLUG,
    has_accounting=False,
    # --gres=gpu:N and --gpus=N both work live; gres matches the node's
    # per-node GRES and keeps --nodes=1 explicit.
    gpu_request_style="gres",
)
register_backend(SLUG, BACKEND)
