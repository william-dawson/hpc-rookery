"""ai-naur (Naur GB300 node) registration for the unified hub.

naur is one aarch64 Ubuntu 24.04 host: 72 Neoverse-V2 cores, ~744 GiB of
memory and one NVIDIA GB300 GPU. It is a compute node of a small Slurm
cluster whose controller is another host (``prado``); the same cluster also
holds ``shannon`` and ``backus``, each alone in a partition named after it.
This facility is naur only, so it targets the ``naur`` partition (the
cluster default) and nothing else. Facts below were read live
(``scontrol show config``/``partition``/``node``, ``nvidia-smi``, dry-run
and real test jobs) on 2026-11-27.

Three properties shape this backend:

- **No usable accounting.** slurm.conf names slurmdbd, but the database
  refuses connections, so ``sacct``/``sacctmgr`` fail. Status therefore
  comes from squeue/scontrol (``has_accounting=False``).
- **Memory cannot be requested.** The node is registered with
  ``RealMemory=1`` and selection is ``CR_CORE``, so ``--mem=1024M`` is
  refused with "Requested node configuration is not available". Jobs share
  the node's memory without a per-job limit.
- **One GPU as an enforced GRES.** ``Gres=gpu:1`` with cgroup
  ``ConstrainDevices=yes``: a job without ``--gres=gpu:1`` gets "No devices
  found" from nvidia-smi, and ``--gres=gpu:2`` is refused at submit.
"""
from pathlib import Path

from hpc_agent_core import config
from hpc_agent_core.compute.slurm import SlurmBackend
from hpc_agent_core.models import JobSpec
from facilities.registry import register_backend

SLUG = "ai-naur"
_PARTITION = "naur"
_CPUS = 72                       # 72 cores, one thread each

FACILITY = config.register_facility(
    slug=SLUG,
    display_name="ai-Naur (Naur GB300 node)",
    description="One aarch64 Ubuntu node (72 Neoverse-V2 cores, ~744 GiB) "
                "with a single NVIDIA GB300 GPU (~251 GiB) requested as "
                "--gres=gpu:1 on its own 'naur' Slurm partition; no usable "
                "accounting and no --mem requests; NVIDIA HPC SDK 26.9 and "
                "CUDA 13.2 via environment modules.",
    default_host="ai-Naur",
    data_dir=Path(__file__).parent / "data",
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",
    embed_model="bge-m3:567m",
    docs_cite_url="",
    config_example={"ssh": {"host": "ai-Naur"}},
    setup_help=(
        "naur needs non-interactive key-based SSH; the MCP server cannot\n"
        "answer a password prompt. Add an 'ai-Naur' Host alias to\n"
        "~/.ssh/config with the HostName, User and IdentityFile the machine's\n"
        "administrator gave you, and check that `ssh ai-Naur hostname` prints\n"
        "'naur' without prompting. No project/account is needed: Slurm's\n"
        "accounting database is not in service. Running on naur itself? Use\n"
        "host=localhost."
    ),
)


class AiNaurBackend(SlurmBackend):
    _NO_ACCOUNTING = (
        "Slurm's accounting database is not reachable from naur, so there "
        "are no projects or allocations to report"
    )

    def get_projects(self) -> list[dict]:
        raise self._unsupported("project listing", self._NO_ACCOUNTING)

    def get_project_allocations(self, project_id: str) -> dict:
        raise self._unsupported("project allocations", self._NO_ACCOUNTING)

    def get_user_allocations(self, project_id: str) -> dict:
        raise self._unsupported("user allocations", self._NO_ACCOUNTING)

    def apply_defaults(self, spec: JobSpec) -> None:
        """This facility is the naur partition, so a blank queue means it."""
        if not spec.attributes.queue_name:
            spec.attributes.queue_name = _PARTITION

    def validate_spec(self, spec: JobSpec) -> None:
        attrs, resources = spec.attributes, spec.resources
        if attrs.queue_name != _PARTITION:
            raise ValueError(
                f"This facility submits to one Slurm partition, {_PARTITION!r}. "
                f"Set spec.attributes.queue_name to {_PARTITION!r} or leave it "
                f"blank; got {attrs.queue_name!r}. (The other partitions "
                "sinfo lists are different machines, not naur.)"
            )
        if attrs.account:
            raise ValueError(
                "naur's Slurm has no working accounting, so there are no "
                "projects to bill. Leave spec.attributes.account unset."
            )
        if resources.node_count != 1:
            raise ValueError(
                "naur is a single node. Set resources.node_count=1."
            )
        if resources.memory:
            raise ValueError(
                "Leave resources.memory unset on naur. The node is registered "
                "in Slurm with 1 MiB of memory, so any --mem request is "
                "refused at submit; jobs share the node's ~744 GiB without a "
                "per-job limit."
            )
        if resources.gpu_cores_per_process:
            raise ValueError(
                "gpu_cores_per_process is not mapped on naur. Use "
                "resources.gpus (0 or 1) instead."
            )
        if resources.gpus and resources.gpus > 1:
            raise ValueError(
                f"naur has one GPU (NVIDIA GB300); got gpus={resources.gpus}. "
                "Set resources.gpus to 0 or 1; Slurm refuses gpu:2 at submit."
            )
        if spec.container is not None:
            raise ValueError(
                "naur has no Singularity/Apptainer, which is what container "
                "jobs render to. Run software installed on the host or built "
                "under ~/agent/work/ instead."
            )
        tasks = resources.processes_per_node
        if resources.process_count is not None:
            tasks = resources.process_count
        requested = tasks * (resources.cpu_cores_per_process or 1)
        if requested > _CPUS:
            raise ValueError(
                f"naur has {_CPUS} CPU cores but this shape requests "
                f"{requested}. Reduce process_count/processes_per_node or "
                "cpu_cores_per_process."
            )
        # MaxTime is UNLIMITED on the naur partition, so duration needs no
        # check here.


BACKEND = AiNaurBackend(
    facility=SLUG,
    has_accounting=False,
    # --gres=gpu:N and --gpus=N are both accepted (dry-run verified); gres
    # matches the node's per-node GRES and keeps --nodes=1 explicit.
    gpu_request_style="gres",
)
register_backend(SLUG, BACKEND)
