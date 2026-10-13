"""Dual Grid Engine + Slurm backend for cell2026."""
from __future__ import annotations

import logging
import re
import time

from hpc_agent_core.compute.base import SchedulerBackend
from hpc_agent_core.compute.gridengine import GridEngineBackend
from hpc_agent_core.compute.slurm import SlurmBackend
from hpc_agent_core.middleware import run_command
from hpc_agent_core.models import Job, JobAttributes, JobSpec, JobState, JobStatus, Scheduler
from facilities.cell2026 import registry

_LOG = logging.getLogger(__name__)
_GE_QUEUES = frozenset({"helix", "kinase", "all.q", "gpu"})
_SLURM_QUEUES = frozenset({"beta", "serine", "all"})
_GE_HOSTS = frozenset({"helix", "kinase"})
_SLURM_HOSTS = frozenset({"beta", "serine"})
_GE_PARALLEL_ENVS = frozenset({
    "smp", "OpenMP", "mpi", "mpi1", "mpi2", "mpi4", "mpi8", "mpi16", "mpi32",
})
_ENV_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _duration_seconds(value: int | str) -> int:
    if isinstance(value, int):
        return value
    days = 0
    clock = value
    if "-" in clock:
        day_text, clock = clock.split("-", 1)
        days = int(day_text)
    hours, minutes, seconds = (int(part) for part in clock.split(":"))
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


class Cell2026SlurmBackend(SlurmBackend):
    """Slurm here has neither usable RealMemory nor GPU GRES."""

    def _header(self, spec: JobSpec) -> list[str]:
        return [line for line in super()._header(spec)
                if not line.startswith("#SBATCH --mem=")]


class Cell2026GridEngineBackend(GridEngineBackend):
    """Map threaded PSI/J shapes to GE slots and OMP_NUM_THREADS."""

    @staticmethod
    def _threaded_spec(spec: JobSpec) -> JobSpec:
        cores = spec.resources.cpu_cores_per_process
        if not cores:
            return spec
        environment = dict(spec.environment)
        environment.setdefault("OMP_NUM_THREADS", str(cores))
        if spec.attributes.parallel_env not in {"smp", "OpenMP"}:
            return spec.model_copy(update={"environment": environment})
        tasks = (spec.resources.process_count or
                 spec.resources.node_count * spec.resources.processes_per_node)
        resources = spec.resources.model_copy(update={"process_count": tasks * cores})
        return spec.model_copy(update={
            "resources": resources, "environment": environment,
        })

    def render_script(self, spec: JobSpec) -> str:
        return super().render_script(self._threaded_spec(spec))


class Cell2026Backend(SchedulerBackend):
    def __init__(self, facility: str, ge_bin_prefix: str = ""):
        super().__init__(facility=facility, name="gridengine+slurm")
        self._slurm = Cell2026SlurmBackend(
            facility=facility,
            name="slurm",
            has_accounting=False,
            gpu_request_style="gres",
            no_gpu_flag_prefixes=frozenset({""}),
            jobs_dir="agent/jobs",
        )
        self._gridengine = Cell2026GridEngineBackend(
            facility=facility,
            name="gridengine",
            default_queue="all.q",
            default_pe="smp",
            host_pins=set(_GE_HOSTS),
            queue_aliases={"gpu"},
            bin_prefix=ge_bin_prefix,
            jobs_dir="agent/jobs",
        )

    @staticmethod
    def _requested_scheduler(
        spec_or_attrs: JobSpec | JobAttributes,
    ) -> str | None:
        attrs = (spec_or_attrs.attributes
                 if isinstance(spec_or_attrs, JobSpec) else spec_or_attrs)
        override = attrs.scheduler
        queue = attrs.queue_name
        if override is not None:
            selected = "slurm" if override == Scheduler.SLURM else "gridengine"
            if queue:
                matching = "slurm" if queue in _SLURM_QUEUES else (
                    "gridengine" if queue in _GE_QUEUES else None)
                if matching is None:
                    raise ValueError(
                        f"Unknown cell2026 queue/host selector {queue!r}. Use "
                        f"one of {sorted(_GE_QUEUES | _SLURM_QUEUES)}."
                    )
                if matching != selected:
                    raise ValueError(
                        f"cell2026 scheduler={selected!r} conflicts with "
                        f"queue_name={queue!r}, which belongs to {matching}."
                    )
            return selected
        if queue in _SLURM_QUEUES:
            return "slurm"
        if queue in _GE_QUEUES:
            return "gridengine"
        if queue:
            raise ValueError(
                f"Unknown cell2026 queue/host selector {queue!r}. Use one of "
                f"{sorted(_GE_QUEUES | _SLURM_QUEUES)}."
            )
        return None

    def _select(self, spec_or_attrs: JobSpec | JobAttributes):
        scheduler = self._requested_scheduler(spec_or_attrs)
        if scheduler is None:
            # apply_defaults normally resolves this. Direct backend callers
            # retain the documented Grid Engine default.
            scheduler = "gridengine"
        return self._slurm if scheduler == "slurm" else self._gridengine

    def _normalized(self, spec: JobSpec) -> JobSpec:
        """Translate host aliases to each scheduler's real queue/partition."""
        scheduler = self._requested_scheduler(spec) or "gridengine"
        attrs = spec.attributes
        custom = dict(attrs.custom_attributes)
        queue = attrs.queue_name
        if scheduler == "slurm":
            if queue in _SLURM_HOSTS:
                existing = custom.get("nodelist")
                if existing and existing != queue:
                    raise ValueError(
                        f"queue_name={queue!r} conflicts with custom nodelist={existing!r}."
                    )
                custom["nodelist"] = queue
                queue = "all"
            elif not queue:
                queue = "all"
        else:
            if not queue:
                queue = "all.q"
        if queue == attrs.queue_name and custom == attrs.custom_attributes:
            return spec
        return spec.model_copy(update={
            "attributes": attrs.model_copy(update={
                "queue_name": queue, "custom_attributes": custom,
            }),
        })

    def validate_spec(self, spec: JobSpec) -> None:
        scheduler = self._requested_scheduler(spec)
        if scheduler is None:
            scheduler = "gridengine"
        attrs, resources = spec.attributes, spec.resources
        if attrs.account:
            raise ValueError(
                "cell2026 has no accounts on either scheduler. Leave "
                "attributes.account unset."
            )
        for key in spec.environment:
            if not _ENV_RE.fullmatch(key):
                raise ValueError(f"Invalid shell environment variable name {key!r}.")
        if resources.memory is not None:
            raise ValueError(
                "cell2026 does not accept generic memory requests: Grid Engine "
                "has no mapped memory complex here and Slurm has RealMemory=1. "
                "Leave resources.memory unset."
            )
        if resources.gpu_cores_per_process:
            raise ValueError(
                "Use job-total resources.gpus on cell2026; "
                "gpu_cores_per_process is not mapped by either scheduler."
            )
        if scheduler == "gridengine":
            if attrs.parallel_env not in _GE_PARALLEL_ENVS:
                raise ValueError(
                    f"Unknown cell2026 Grid Engine parallel_env {attrs.parallel_env!r}. "
                    f"Use one of {sorted(_GE_PARALLEL_ENVS)}."
                )
            if resources.gpus > 2:
                raise ValueError(
                    "helix and kinase each expose two RTX A4000 GPUs. Set "
                    "resources.gpus to 0, 1, or 2."
                )
            if resources.gpus and resources.node_count != 1:
                raise ValueError(
                    "A cell2026 Grid Engine GPU request is allocated on one "
                    "helix/kinase host. Set node_count=1; use a verified MPI "
                    "shape separately for multi-host CPU work."
                )
            if resources.node_count > 2:
                raise ValueError(
                    "cell2026 Grid Engine has two execution hosts; request at most two."
                )
            if attrs.queue_name in _GE_HOSTS and resources.node_count != 1:
                raise ValueError(
                    f"Host selector {attrs.queue_name!r} pins one Grid Engine "
                    "host, so node_count must be 1."
                )
            tasks = (resources.process_count or
                     resources.node_count * resources.processes_per_node)
            slots = tasks
            if attrs.parallel_env in {"smp", "OpenMP"}:
                slots *= resources.cpu_cores_per_process or 1
            if attrs.queue_name in _GE_HOSTS and slots > 32:
                raise ValueError(
                    f"Host {attrs.queue_name!r} has 32 CPU cores, but this "
                    f"shape requests {slots} Grid Engine slots. Reduce the "
                    "process shape or use all.q with a verified MPI PE."
                )
            if attrs.parallel_env in {"smp", "OpenMP"} and slots > 32:
                raise ValueError(
                    f"cell2026 {attrs.parallel_env} jobs are single-host and "
                    f"limited to 32 slots; got {slots}."
                )
            if slots > 64:
                raise ValueError(
                    f"cell2026 Grid Engine has 64 CPU cores across helix and "
                    f"kinase, but this shape requests {slots} slots."
                )
            if resources.exclusive_node_use:
                raise ValueError(
                    "exclusive_node_use is not mapped by the cell2026 Grid "
                    "Engine backend. Leave it false."
                )
            if attrs.reservation_id:
                raise ValueError(
                    "reservation_id is not mapped on cell2026 Grid Engine. "
                    "Leave it unset."
                )
            if attrs.custom_attributes:
                raise ValueError(
                    "cell2026 Grid Engine custom_attributes are not mapped. "
                    "Use queue_name and parallel_env instead."
                )
            if spec.stdin_path:
                raise ValueError(
                    "stdin_path is not mapped on cell2026 Grid Engine. Redirect "
                    "input explicitly in the executable."
                )
            if resources.gpus and "CUDA_VISIBLE_DEVICES" in spec.environment:
                raise ValueError(
                    "Do not set CUDA_VISIBLE_DEVICES for a cell2026 Grid Engine "
                    "GPU job. The backend derives it from $SGE_HGR_gpu."
                )
            if _duration_seconds(attrs.duration) > 5 * 86400:
                raise ValueError(
                    "The recorded cell2026 Grid Engine wall-time limit is five "
                    "days. Reduce attributes.duration."
                )
        else:
            custom = attrs.custom_attributes
            if set(custom) - {"nodelist"}:
                raise ValueError(
                    "cell2026 Slurm supports only custom_attributes.nodelist; "
                    "other raw #SBATCH options are not emitted by this port."
                )
            if "nodelist" in custom and custom["nodelist"] not in _SLURM_HOSTS:
                raise ValueError(
                    f"cell2026 Slurm nodelist must be one of {sorted(_SLURM_HOSTS)}."
                )
            if (attrs.queue_name in _SLURM_HOSTS and custom.get("nodelist")
                    and custom["nodelist"] != attrs.queue_name):
                raise ValueError(
                    "The Slurm host selected by queue_name conflicts with nodelist."
                )
            if resources.node_count > 2:
                raise ValueError("cell2026 Slurm has two nodes; request at most two.")
            if attrs.queue_name in _SLURM_HOSTS and resources.node_count != 1:
                raise ValueError(
                    f"Host selector {attrs.queue_name!r} pins one Slurm node, "
                    "so node_count must be 1."
                )
            tasks = resources.process_count or (
                resources.node_count * resources.processes_per_node)
            cores = tasks * (resources.cpu_cores_per_process or 1)
            if cores > resources.node_count * 8:
                raise ValueError(
                    f"cell2026 Slurm exposes 8 CPU cores per node, but this "
                    f"shape requests {cores} across {resources.node_count} node(s)."
                )
            if resources.gpus > 1 or (resources.gpus and resources.node_count != 1):
                raise ValueError(
                    "A cell2026 Slurm node has one unmanaged GPU. "
                    "resources.gpus may only be 1 on a one-node job, and only "
                    "toggles container --nv; it does not reserve or isolate a GPU."
                )
            if resources.gpus and spec.container is None:
                raise ValueError(
                    "resources.gpus has no scheduler effect on cell2026 Slurm. "
                    "Use beta/serine to select the unmanaged GPU host and leave "
                    "gpus unset, or set gpus=1 only on a Singularity job where "
                    "it enables --nv."
                )
            if "parallel_env" in attrs.model_fields_set:
                raise ValueError(
                    "parallel_env is Grid Engine-only. Leave it unset for "
                    "cell2026 Slurm jobs."
                )

    def render_script(self, spec: JobSpec) -> str:
        self.validate_spec(spec)
        normalized = self._normalized(spec)
        return self._select(normalized).render_script(normalized)

    def submit(self, spec: JobSpec) -> dict:
        self.validate_spec(spec)
        normalized = self._normalized(spec)
        backend = self._select(normalized)
        result = backend.submit(normalized)
        job_id = result.get("job_id", "")
        if job_id:
            registry.record(
                job_id, backend.name, normalized.attributes.queue_name,
                result.get("script_path"),
            )
        return result

    @staticmethod
    def _scheduler_answered(backend, probe: str) -> tuple[bool, str]:
        """Positive evidence that `backend`'s scheduler is actually reachable.

        Returns (ok, reason_if_not). Used only on the destructive cancel
        path, where "no answer" must never be read as "no such job" — see
        cancel(). A cheap version/help probe is enough: it goes through the
        same run_command/SSH path the real query would, and unlike the
        status queries it is not wrapped in the backends' own error
        swallowing.
        """
        from hpc_agent_core.middleware import run_command
        try:
            run_command(backend.facility, probe)
        except Exception as exc:  # noqa: BLE001 -- any failure means "unknown"
            return False, f"{type(exc).__name__}: {str(exc)[:120]}"
        return True, ""

    @staticmethod
    def _is_not_found(job: Job, scheduler: str) -> bool:
        status = job.status
        if status is None or status.state != JobState.UNKNOWN:
            return False
        meta = status.meta_data or {}
        if scheduler == "slurm":
            return not meta.get("native_state") and not meta.get("partition")
        return not meta.get("native_state") and not meta.get("queue")

    @staticmethod
    def _tag(job: Job, key: str, value) -> Job:
        if not job.status:
            return job
        meta = dict(job.status.meta_data or {})
        meta[key] = value
        return job.model_copy(update={
            "status": job.status.model_copy(update={"meta_data": meta}),
        })

    def get_statuses(self, job_ids: list[str]) -> list[Job]:
        groups = {"slurm": [], "gridengine": [], "unknown": []}
        for job_id in job_ids:
            scheduler = registry.lookup(job_id)
            groups[scheduler if scheduler in {"slurm", "gridengine"} else "unknown"].append(job_id)
        found = {}
        for scheduler, backend in (("slurm", self._slurm),
                                   ("gridengine", self._gridengine)):
            if groups[scheduler]:
                for job in backend.get_statuses(groups[scheduler]):
                    found[job.id] = self._tag(job, "scheduler_source", "registry")
        if groups["unknown"]:
            slurm = {job.id: job for job in self._slurm.get_statuses(groups["unknown"])
                     if not self._is_not_found(job, "slurm")}
            ge = {job.id: job for job in self._gridengine.get_statuses(groups["unknown"])
                  if not self._is_not_found(job, "gridengine")}
            for job_id in groups["unknown"]:
                if job_id in slurm and job_id in ge:
                    job = self._tag(slurm[job_id], "scheduler_source", "ambiguous")
                    if job.status:
                        job.status.message = (
                            f"Job id {job_id} exists in both schedulers; the "
                            "Slurm result is shown. A registry entry is needed "
                            "for deterministic routing."
                        )
                    found[job_id] = job
                elif job_id in slurm:
                    found[job_id] = self._tag(
                        slurm[job_id], "scheduler_source", "slurm_fallback")
                elif job_id in ge:
                    found[job_id] = self._tag(
                        ge[job_id], "scheduler_source", "gridengine_fallback")
                else:
                    found[job_id] = Job(id=job_id, status=JobStatus(
                        state=JobState.UNKNOWN,
                        message="Job was not found in Slurm or Grid Engine.",
                        meta_data={"scheduler_source": "query_both", "source": "none"},
                    ))
        return [found[job_id] for job_id in job_ids]

    def get_recent_statuses(self, since: str = "now-2days") -> list[Job]:
        days = 2
        if match := re.fullmatch(r"now-(\d+)days?", since):
            days = int(match.group(1))
        cutoff = time.time() - days * 86400
        ids = [entry["job_id"] for entry in registry.recent(limit=100)
               if entry.get("recorded_at", 0) >= cutoff]
        jobs = self.get_statuses(ids) if ids else []
        seen = {job.id for job in jobs}
        for backend in (self._slurm, self._gridengine):
            try:
                live = backend.get_recent_statuses()
            except Exception as exc:  # noqa: BLE001
                _LOG.warning("cell2026 %s live query failed: %s", backend.name, exc)
                continue
            for job in live:
                if job.id not in seen:
                    jobs.append(job)
                    seen.add(job.id)
        return jobs

    def cancel(self, job_id: str) -> Job | str:
        scheduler = registry.lookup(job_id)
        if scheduler == "slurm":
            return self._slurm.cancel(job_id)
        if scheduler == "gridengine":
            return self._gridengine.cancel(job_id)
        # An ID can exist independently in both schedulers. Identify it with
        # read-only queries before issuing either destructive cancel command.
        #
        # Fail closed on an inconclusive lookup. _is_not_found() cannot tell
        # "this scheduler does not have the job" from "the query failed" —
        # both surface as UNKNOWN with no queue/partition metadata — and this
        # facility's Slurm runs has_accounting=False, whose squeue *and*
        # scontrol failures are both swallowed internally, so a dead
        # connection returns UNKNOWN rather than raising. Without a positive
        # liveness check, a failed Grid Engine lookup would silently collapse
        # the "exists in both, refuse" guard into cancelling on whichever
        # scheduler answered — and since ids can collide across the two, that
        # can cancel a different job.
        slurm_live, slurm_why = self._scheduler_answered(self._slurm, "sinfo --version")
        ge_live, ge_why = self._scheduler_answered(self._gridengine, "qstat -help")
        if not (slurm_live and ge_live):
            dead = "Slurm" if not slurm_live else "Grid Engine"
            why = slurm_why if not slurm_live else ge_why
            raise ValueError(
                f"Refusing to cancel unregistered job {job_id!r}: the {dead} "
                f"lookup on cell2026 could not be completed ({why}), so it is "
                "impossible to tell whether that scheduler also holds this id. "
                "Job ids can collide between the two schedulers here, so "
                "cancelling on the one that did answer risks killing a "
                "different job. Fix the connection, or name the scheduler "
                "explicitly via the job registry."
            )

        slurm_status = self._slurm.get_statuses([job_id])[0]
        ge_status = self._gridengine.get_statuses([job_id])[0]
        slurm_hit = not self._is_not_found(slurm_status, "slurm")
        ge_hit = not self._is_not_found(ge_status, "gridengine")
        if slurm_hit and ge_hit:
            raise ValueError(
                f"Job id {job_id!r} exists in both cell2026 schedulers and has "
                "no local registry entry. Refusing to cancel either one. "
                "Identify the intended scheduler before trying again."
            )
        if slurm_hit:
            result = self._slurm.cancel(job_id)
            return (self._tag(result, "cancel_source", "slurm_fallback")
                    if isinstance(result, Job) else result)
        if ge_hit:
            result = self._gridengine.cancel(job_id)
            return (self._tag(result, "cancel_source", "gridengine_fallback")
                    if isinstance(result, Job) else result)
        return Job(id=job_id, status=JobStatus(
            state=JobState.UNKNOWN,
            message="Neither scheduler found the unregistered job; nothing was canceled.",
            meta_data={"cancel_source": "query_both"},
        ))

    def update(self, job_id: str, spec: JobSpec) -> Job:
        scheduler = registry.lookup(job_id)
        if scheduler is None:
            scheduler = self._requested_scheduler(spec)
        if scheduler is None:
            raise ValueError(
                "The cell2026 scheduler for this unregistered job is unknown. "
                "Set attributes.scheduler or a recognized queue_name on the update spec."
            )
        if scheduler == "gridengine":
            raise self._unsupported(
                "update_job",
                "the mapped Grid Engine backend has no verified generic update operation",
            )
        normalized = (
            self._normalized(spec)
            if "queue_name" in spec.attributes.model_fields_set
            else spec
        )
        return self._slurm.update(job_id, normalized)

    def get_live_resources(self) -> list[dict]:
        """Return occupancy only when both cell2026 schedulers answered.

        Grid Engine and Slurm each cover different nodes at this facility.
        Returning the result from one scheduler, or an empty list after both
        probes fail, would look like a successful complete resource query to
        callers.  That is especially misleading for an unconfigured user:
        ``run_command`` supplies the actionable setup error, but the old
        implementation swallowed it and returned ``[]``.
        """
        resources = []
        failures: list[tuple[str, RuntimeError]] = []
        try:
            for row in self._slurm.get_live_resources():
                resources.append({**row, "scheduler": "slurm"})
        except RuntimeError as exc:
            _LOG.warning("cell2026 Slurm resource query failed: %s", exc)
            failures.append(("Slurm", exc))
        qstat = self._gridengine._qbin("qstat")
        try:
            output = run_command(self.facility, f"{qstat} -g c")
        except RuntimeError as exc:
            _LOG.warning("cell2026 Grid Engine resource query failed: %s", exc)
            failures.append(("Grid Engine", exc))
            output = ""
        for line in output.splitlines():
            fields = line.split()
            if (len(fields) >= 8 and fields[0] != "CLUSTER_QUEUE"
                    and not fields[0].startswith("-") and fields[2].isdigit()):
                resources.append({
                    "partition": fields[0], "scheduler": "gridengine",
                    "cqload": fields[1], "slots_used": int(fields[2]),
                    "slots_reserved": int(fields[3]),
                    "slots_available": int(fields[4]), "slots_total": int(fields[5]),
                    "slots_ao_acds": fields[6], "slots_error": fields[7],
                })
        if failures:
            scheduler_names = ", ".join(name for name, _ in failures)
            raise RuntimeError(
                "cell2026 live resource data is incomplete because the "
                f"following scheduler probe(s) failed: {scheduler_names}. "
                "No occupancy data is returned unless both Grid Engine and "
                "Slurm succeed.\n\n"
                f"{failures[0][1]}"
            ) from failures[0][1]
        return resources

    def get_drained_nodes(self) -> list[dict]:
        return [{**row, "scheduler": "slurm"}
                for row in self._slurm.get_drained_nodes()]

    def get_projects(self) -> list[dict]:
        # Neither scheduler exposes a per-project account query here.  An
        # empty success response would be indistinguishable from a completed
        # query for a user with no accounts, and led clients to infer that
        # the facility was reachable even when it was not configured.
        raise self._unsupported(
            "get_projects",
            "neither Grid Engine nor Slurm exposes per-project accounting",
        )

    def check_scheduler(self) -> bool:
        from hpc_agent_core.doctor import check_commands_on_path
        ge_commands = [
            self._gridengine._qbin(command)
            for command in ("qsub", "qstat", "qacct", "qdel", "qhost")
        ]
        return check_commands_on_path(
            self.facility,
            ["sbatch", "squeue", "scontrol", "scancel", "sinfo",
             *ge_commands],
            "gridengine+slurm",
        )
