"""ROQUO (RIKEN R-CCS) — GB200 GPU system, Slurm with accounting.

Two things shape this port:

- ROQUO is a `--gres=gpu:N` facility, unlike RIKYU next door, which uses
  job-total `--gpus=N`. The GPU count is per node here, which is why
  `--nodes` is always emitted (the default `nodes_always_explicit` for the
  "gres" style) rather than letting Slurm derive placement.
- The machine publishes its own rejection codes (ROQUO-E001, E101, E102,
  E103) and has one silent trap — a `work` job over three days without
  `--qos=long` is accepted and then never starts. validate_spec() below
  catches all of those at submit time, because "never starts" is
  indistinguishable from "queued" to anyone watching.
"""
import os
from pathlib import Path

from hpc_agent_core import config
from hpc_agent_core.compute.slurm import SlurmBackend
from hpc_agent_core.middleware import run_command
from hpc_agent_core.models import JobSpec
from facilities.registry import register_backend

SLUG = "roquo"

FACILITY = config.register_facility(
    slug=SLUG,
    display_name="ROQUO (RIKEN R-CCS)",
    description="GB200 GPU system with aarch64 compute nodes and x86_64 "
                "login/work nodes, Slurm with accounting, --gres=gpu:N and "
                "QOS-tiered wall times.",
    default_host="login.roquo.qc.r-ccs.riken.jp",
    data_dir=Path(__file__).parent / "data",
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",
    embed_model="bge-m3:567m",
    docs_cite_url="",
    config_example={
        "ssh": {"host": "login.roquo.qc.r-ccs.riken.jp", "user": "<your-username>"},
        "defaults": {"account": "<your-project>"},
    },
    setup_help=(
        "Register your public key yourself in the ROQUO Portal\n"
        "(https://portal.roquo.qc.r-ccs.riken.jp/) under 'SSH Keys': paste the\n"
        "contents of your .pub file and press Add. If that screen says keys\n"
        "cannot be changed there, open a portal ticket instead.\n"
        "\n"
        "Set defaults.account to the project you want billed. ROQUO uses it for\n"
        "both billing and the group that owns files your jobs write, and a job\n"
        "without it silently falls back to a restrictive default account rather\n"
        "than failing. `sacctmgr -nP show assoc user=$USER format=Account` on\n"
        "the login node lists what you may charge.\n"
        "\n"
        "Login nodes are x86_64 and compute nodes are aarch64, so anything you\n"
        "build on a login node will not run on a compute node."
    ),
)

#: Partitions that exist. Submitting to anything else is a typo or a stale
#: script from before the per-rack partitions were withdrawn.
_PARTITIONS = frozenset({"roquo", "work"})

#: Removed 2026-10-13. Worth naming explicitly: an old script fails with a
#: bare Slurm "invalid partition" that doesn't say what to use instead.
_REMOVED_RACK_PARTITIONS = frozenset(f"roquo-rack{n:02d}" for n in range(1, 9))

#: Which QOS each partition accepts, read live from `scontrol show
#: partition` (AllowQos). The manual lists only normal/p1/p2/p3 for roquo
#: and implies long is work-only; live adds p4 and p5 on both. A `general`
#: QOS also exists in sacctmgr but is in neither partition's AllowQos, so
#: it is correctly refused here.
_PARTITION_QOS = {
    "roquo": frozenset({"normal", "p1", "p2", "p3", "p4", "p5"}),
    "work": frozenset({"normal", "long", "p4", "p5"}),
}

#: Per-QOS wall-time ceilings in seconds, from `sacctmgr show qos`
#: (MaxWall). p4 and p5 carry no MaxWall, so only the partition's own
#: MaxTime bounds them -- they are deliberately absent rather than
#: given a guessed value.
_QOS_MAX_WALL = {
    "normal": 3 * 86400,
    "p1": 2 * 86400,
    "p2": 1 * 86400,
    "p3": 12 * 3600,
    "long": 30 * 86400,
}

#: Each partition's own MaxTime. Slurm rejects a job exceeding this at
#: submit time with a clear message; exceeding the *QOS* ceiling while
#: still inside this one is the dangerous case -- see _check_wall_time.
_PARTITION_MAX_WALL = {"roquo": 3 * 86400, "work": 30 * 86400}

_GPUS_PER_NODE = 4
_WORK_MAX_CPUS = 192
_WORK_GIB_PER_CPU = 8
_THREE_DAYS = 3 * 86400
_LONG_QOS_MAX_CPUS = 4
_LONG_QOS_MAX_GIB = 8


def _default_account() -> str | None:
    """The project to bill, from the user's own settings.

    ROQUO_ACCOUNT > defaults.account in the user's config file. Unlike
    HBW2, a missing account is not fatal here: ROQUO accepts the job and
    charges a restrictive default instead. apply_defaults() therefore fills
    this in when it can and stays quiet when it can't, so a user who has
    not set one can still submit — the skills tell the agent to resolve a
    project with get_projects() rather than letting that default happen.
    """
    cfg = config.file_config(SLUG)
    return (os.environ.get(f"{FACILITY.env_prefix}_ACCOUNT")
            or (cfg.get("defaults") or {}).get("account"))


def _gib(num_bytes: int) -> float:
    return num_bytes / 1024 ** 3


class RoquoBackend(SlurmBackend):
    def apply_defaults(self, spec: JobSpec) -> None:
        attrs = spec.attributes
        if not attrs.queue_name:
            attrs.queue_name = "roquo"
        if attrs.account is None:
            attrs.account = _default_account()

    def get_projects(self) -> list[dict]:
        """Slurm associations, with the unchargeable personal one flagged.

        `sacctmgr` lists two associations for a ROQUO user: a billing group
        and a personal account named after the username. Submitting against
        the personal one is refused outright with ROQUO-E202 ("Jobs cannot
        be submitted with a personal account"), so returning both
        undifferentiated invites an agent to pick the wrong one -- and the
        personal account tends to sort first.
        """
        projects = super().get_projects()
        username = run_command(self.facility, "id -un").strip()
        for project in projects:
            personal = project.get("account") == username
            project["chargeable"] = not personal
            if personal:
                project["note"] = (
                    "Personal account — cannot be charged. ROQUO refuses a job "
                    "submitted against it with ROQUO-E202; use a billing group."
                )
        return projects

    def validate_spec(self, spec: JobSpec) -> None:
        attrs = spec.attributes
        res = spec.resources
        queue = attrs.queue_name
        gpus = res.gpus or res.gpu_cores_per_process or 0
        qos = attrs.custom_attributes.get("qos", "")
        duration = self._duration_seconds(attrs.duration)

        if queue in _REMOVED_RACK_PARTITIONS:
            raise ValueError(
                f"Partition {queue!r} was removed on 2026-10-13. Submit to "
                "'roquo' instead, and add custom_attributes {'switches': '1'} "
                "if the job needs its nodes inside a single rack."
            )
        if queue not in _PARTITIONS:
            raise ValueError(
                f"Unknown ROQUO partition {queue!r}. Valid partitions: "
                f"{', '.join(sorted(_PARTITIONS))}."
            )

        if queue == "work":
            self._validate_work(spec, gpus, qos, duration)
        else:
            self._validate_roquo(spec, gpus, qos, duration)

    # -- per-partition rules, split because the two are different machines --

    def _validate_roquo(self, spec: JobSpec, gpus: int, qos: str,
                        duration: int | None) -> None:
        if gpus > _GPUS_PER_NODE:
            raise ValueError(
                f"A single --gres request cannot exceed one node's "
                f"{_GPUS_PER_NODE} GPUs (ROQUO-E001); got {gpus}. ROQUO's GPU "
                "count is per node, so for more GPUs set resources.gpus=4 and "
                "resources.node_count to the number of nodes you want."
            )
        # No node-count check: the roquo partition reports
        # MaxNodes=UNLIMITED and the `normal` QOS sets no cap. The 36-node
        # figure in the manual is the `general` QOS's MaxNodesPerJob, and
        # `general` is not in this partition's AllowQos at all -- enforcing
        # it here would reject jobs the scheduler accepts.
        self._check_qos_and_wall_time(spec, "roquo", qos, duration)

    def _validate_work(self, spec: JobSpec, gpus: int, qos: str,
                       duration: int | None) -> None:
        res = spec.resources
        if gpus:
            raise ValueError(
                "The work partition has no GPUs. Submit GPU work to the "
                "'roquo' partition, or drop resources.gpus."
            )
        cpus = res.cpu_cores_per_process or res.process_count
        if not cpus:
            raise ValueError(
                "The work partition requires an explicit CPU count "
                "(ROQUO-E101). Set resources.cpu_cores_per_process (renders as "
                "--cpus-per-task) or resources.process_count (--ntasks), "
                f"1-{_WORK_MAX_CPUS}."
            )
        if cpus > _WORK_MAX_CPUS:
            raise ValueError(
                f"The work partition has {_WORK_MAX_CPUS} logical CPUs per "
                f"node (ROQUO-E102); got {cpus}."
            )
        if res.memory and _gib(res.memory) > cpus * _WORK_GIB_PER_CPU:
            raise ValueError(
                f"Memory on work is capped at {_WORK_GIB_PER_CPU} GiB per "
                f"allocated CPU (ROQUO-E103): {cpus} CPUs allows at most "
                f"{cpus * _WORK_GIB_PER_CPU} GiB, but "
                f"{_gib(res.memory):.1f} GiB was requested."
            )
        if qos == "long":
            if cpus > _LONG_QOS_MAX_CPUS:
                raise ValueError(
                    f"The 'long' QOS limits a job to {_LONG_QOS_MAX_CPUS} CPUs "
                    f"(verified live via sacctmgr MaxTRESPerJob); got {cpus}."
                )
            if res.memory and _gib(res.memory) > _LONG_QOS_MAX_GIB:
                raise ValueError(
                    f"The 'long' QOS limits a job to {_LONG_QOS_MAX_GIB} GiB; "
                    f"got {_gib(res.memory):.1f} GiB."
                )
        self._check_qos_and_wall_time(spec, "work", qos, duration)

    # -- shared QOS / wall-time policy, driven by live scheduler data --

    @staticmethod
    def _check_qos_and_wall_time(spec: JobSpec, partition: str, qos: str,
                                 duration: int | None) -> None:
        """Reject a QOS the partition won't take, and the silent park.

        Two different failures hide here, and only one of them is loud:

        - Over the *partition's* MaxTime, Slurm refuses the job at submit
          with a clear message. Pre-empting it is a convenience.
        - Over the selected *QOS's* MaxWall while still inside the
          partition's MaxTime, Slurm accepts the job and then never
          schedules it, parking it on QOSMaxWallDurationPerJobLimit. From
          the outside that is indistinguishable from a busy queue, so it
          has to be caught here or not at all. On `work` that is any run
          over 3 days without --qos=long; on `roquo` it is equally real
          for p1/p2/p3, whose ceilings sit below the partition's 3 days.
        """
        allowed = _PARTITION_QOS[partition]
        if qos and qos not in allowed:
            raise ValueError(
                f"QOS {qos!r} is not accepted by the {partition!r} partition. "
                f"It allows: {', '.join(sorted(allowed))}."
            )
        if duration is None:
            return

        partition_cap = _PARTITION_MAX_WALL[partition]
        if duration > partition_cap:
            raise ValueError(
                f"Wall time {spec.attributes.duration!r} exceeds the "
                f"{partition!r} partition's own limit of "
                f"{partition_cap // 86400}d, which Slurm rejects at submit."
            )

        qos_cap = _QOS_MAX_WALL.get(qos or "normal")
        if qos_cap is not None and duration > qos_cap:
            hint = ("Add custom_attributes {'qos': 'long'} for up to 30 days "
                    f"-- which also caps the job at {_LONG_QOS_MAX_CPUS} CPUs "
                    f"and {_LONG_QOS_MAX_GIB} GiB."
                    if partition == "work" else
                    "Pick a QOS whose ceiling covers it (normal=3d, p1=2d, "
                    "p2=1d, p3=12h), or shorten the job.")
            raise ValueError(
                f"Wall time {spec.attributes.duration!r} is over the "
                f"{qos or 'normal'} QOS ceiling of "
                f"{qos_cap // 3600}h, which the scheduler accepts and then "
                "never starts -- the job sits on "
                f"QOSMaxWallDurationPerJobLimit indefinitely. {hint}"
            )

    @staticmethod
    def _duration_seconds(duration: int | str) -> int | None:
        """Seconds for a JobAttributes.duration, or None if unparseable.

        An int is seconds (the IRI convention the models use). A string
        follows Slurm's own --time grammar, which is not simply
        right-padded HH:MM:SS:

            minutes | minutes:seconds | hours:minutes:seconds
            days-hours | days-hours:minutes | days-hours:minutes:seconds

        So a bare "90" is ninety *minutes*, not ninety hours — getting that
        backwards would reject valid jobs here and, worse, let the work
        partition's silent over-three-days trap through.

        Returning None rather than raising keeps validation focused: a
        malformed duration is the shared model's problem to report, not
        this facility's.
        """
        if isinstance(duration, bool):
            return None
        if isinstance(duration, int):
            return duration
        text = str(duration).strip()
        if not text:
            return None

        days = 0
        if "-" in text:
            head, _, text = text.partition("-")
            if not head.isdigit():
                return None
            days = int(head)
            fields = text.split(":") if text else ["0"]
            if len(fields) > 3:
                return None
            fields += ["0"] * (3 - len(fields))      # DD-HH[:MM[:SS]]
        else:
            fields = text.split(":")
            if len(fields) == 1:
                fields = ["0", fields[0], "0"]       # MM
            elif len(fields) == 2:
                fields = ["0", fields[0], fields[1]]  # MM:SS
            elif len(fields) != 3:
                return None                           # HH:MM:SS otherwise

        if not all(f.isdigit() for f in fields):
            return None
        hours, minutes, seconds = (int(f) for f in fields)
        return days * 86400 + hours * 3600 + minutes * 60 + seconds


BACKEND = RoquoBackend(
    facility=SLUG,
    has_accounting=True,
    gpu_request_style="gres",
)
register_backend(SLUG, BACKEND)
