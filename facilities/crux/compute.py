"""PBS Professional backend for ALCF Crux.

Crux is scheduled by Altair PBS Professional 2022.1 — the same product
family as JCAHPC Miyabi's scheduler, but a genuinely different site
dialect, so this is a fresh `SchedulerBackend` subclass rather than a
subclass of Miyabi's backend (PORTING.md §0a: keep it in your facility
until the dialect is shared; the two differ in almost every command):

- account: `#PBS -A <project>` (ALCF sbank projects), not Miyabi's
  `#PBS -W group_list=<group>`;
- select: `-l select=<N>:system=crux` with `-l place=scatter` — whole-node
  scheduling, no mpiprocs/ompthreads chunk fields;
- two more directives are mandatory at ALCF: `-l walltime` and
  `-l filesystems=<home and/or eagle>`;
- status comes from `qstat -fx -F JSON` (full records, finished jobs, no
  fixed-width truncation), not a site history wrapper;
- accounting is ALCF's sbank (`sbank-list-allocations` / `sbank-list-jobs`),
  not sacct-style associations.

Two ALCF behaviours shape this module beyond plain command mapping:

- **The routing-queue trap.** `qsub` into the `workq-route` routing queue
  returns a job id before routing happens; if the job then fits no
  execution queue it is dropped silently and never appears in qstat.
  That is why `validate_spec()` checks node count and walltime against the
  bundled queue limits offline — the failure mode it prevents produces no
  server-side error at all.
- **Forced `-k doe`.** The server adds and enforces direct streaming of
  stdout/stderr to the directory `qsub` ran in. `submit()` deliberately runs
  `qsub` from the job script's own directory (`~/agent/jobs`), so output
  lands beside the script as `<name>.o<seq>` / `<name>.e<seq>` instead of
  loose in the home root, without needing any `-o`/`-e` directives.

Nothing here is guessed: command shapes come from ALCF's published Crux/PBS
documentation and the PBS Professional 2022.1 reference (ALCF runs a
newer 2026.1, same grammar), and the whole surface was live-validated on
2026-11-02 — doctor, read-only smoke (get_resources/get_projects/search_docs
over the real sbank and pbsnodes), and real one-node debug jobs submitted,
polled to completion, and read back through the tools. Three live findings
are baked in: ALCF's sbank adds a Suballocation column (parsed by shape, not
position), `qstat -Q` truncates its Type column with a trailing '*', and a
finished job's history record drops Variable_List entirely — workdir falls
back to Output_Path's directory, which history always keeps.
"""
from __future__ import annotations

import json
import posixpath
import re
import shlex
import time

from hpc_agent_core.compute.base import (
    SchedulerBackend,
    render_body,
)
from hpc_agent_core.middleware import norm_path, run_command, write_remote_file
from hpc_agent_core.models import Job, JobSpec, JobState, JobStatus

#: How many job ids go into one `qstat -fx -F JSON` call when listing recent
#: jobs. Full records are a few KB each and a single reply is capped by
#: middleware's output limit, so the list is fetched in modest batches.
_QSTAT_BATCH = 10

#: Normalized PBS job-state letters (PBS Professional 2022.1 "Job States").
_PBS_STATES = {
    "B": JobState.ACTIVE,       # array job has a running subjob
    "E": JobState.ACTIVE,       # exiting after having run
    "F": JobState.COMPLETED,    # finished
    "H": JobState.HELD,
    "M": JobState.UNKNOWN,      # moved to another server (peer scheduling)
    "Q": JobState.QUEUED,
    "R": JobState.ACTIVE,
    "S": JobState.HELD,         # suspended
    "T": JobState.QUEUED,      # being moved / in transit
    "U": JobState.HELD,         # cycle-harvesting job suspended
    "W": JobState.QUEUED,       # waiting for its start time
    "X": JobState.COMPLETED,    # subjob finished
}

#: The scheduler's own deletion-comment prefix (the literal text ALCF
#: documents for preemption). A functional interface fact, not prose.
_SCHEDULER_DELETE_MARKER = "at request of scheduler"

#: `#PBS -A` takes a bare project identifier; anything with whitespace or
#: shell punctuation would either split the directive into extra options
#: or worse. ALCF project names observed in the wild fit this class
#: (`Catalyst`, `datascience`, `RL-fold`, ...).
_ACCOUNT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")

#: Same reasoning for `#PBS -q`, which carries either a production queue
#: name or a reservation's queue name.
_QUEUE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")

#: The only filesystems ALCF's docs name for Crux; also the vocabulary of
#: the mandatory `-l filesystems` directive.
_KNOWN_FILESYSTEMS = frozenset({"home", "eagle"})


def _duration_seconds(duration: int | str) -> int:
    """JobAttributes.duration (seconds, HH:MM:SS, or D-HH:MM:SS) -> seconds."""
    if isinstance(duration, str):
        days = 0
        body = duration
        if "-" in body:
            days, body = body.split("-", 1)
            days = int(days)
        hours, minutes, seconds = body.split(":")
        return days * 86400 + int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    return int(duration)


def _walltime(duration: int | str) -> str:
    """Duration -> PBS `walltime=HH:MM:SS` (hours may exceed 24; PBS accepts)."""
    total = _duration_seconds(duration)
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _sequence_of(job_id: str) -> str:
    """`12345.crux-pbs-0001...` or bare `12345` -> `12345` (PBS accepts both
    as operands; the sequence number is the untruncated part in list views).
    """
    return job_id.split(".", 1)[0]


def _attr(fields: dict, name: str) -> str:
    """Read one qstat -F JSON job attribute, tolerating the two shapes PBS
    uses for dotted names (flat `"resources_used.walltime"` or a nested
    `"resources_used"` object)."""
    value = fields.get(name)
    if value is None and "." in name:
        outer, _, inner = name.partition(".")
        nested = fields.get(outer)
        if isinstance(nested, dict):
            value = nested.get(inner)
    return "" if value is None else str(value)


class CruxPBSBackend(SchedulerBackend):
    """The ALCF Crux dialect of PBS Professional (see module docstring)."""

    def __init__(self, facility: str, jobs_dir: str = "agent/jobs"):
        super().__init__(facility=facility, name="pbs")
        self._jobs_dir = jobs_dir

    # --- bundled facts ---------------------------------------------------

    @staticmethod
    def _queue_limits() -> dict[str, dict]:
        """Queue name -> recorded node/walltime limits, from the bundled
        facts JSON — so a queue-table change is a data edit, not a code
        edit. Reservation queues are deliberately not in here; they are
        validated only for safe characters."""
        from hpc_agent_core import config
        queues = config.load_facts("crux").get("queues", {})
        return {name: limits for name, limits in queues.items()
                if isinstance(limits, dict)}

    @staticmethod
    def _default_filesystems() -> str:
        from hpc_agent_core import config
        return config.load_facts("crux").get("defaults", {}).get(
            "filesystems", "home:eagle")

    @staticmethod
    def _node_memory_gib() -> int:
        from hpc_agent_core import config
        return int(config.load_facts("crux").get("job_limits", {}).get(
            "node_memory_gib", 256))

    @staticmethod
    def _max_threads_per_node() -> int:
        from hpc_agent_core import config
        return int(config.load_facts("crux").get("job_limits", {}).get(
            "max_threads_per_node", 256))

    # --- validation ------------------------------------------------------

    def _filesystems_of(self, attrs) -> tuple[str, list[str]]:
        """Resolve the filesystems directive: custom_attributes override,
        bundled default otherwise; reject anything outside the known set
        (it is rendered verbatim into a directive line)."""
        unknown = [key for key in attrs.custom_attributes
                   if key != "filesystems"]
        if unknown:
            raise ValueError(
                f"Crux maps no custom attribute(s) {sorted(unknown)} onto a "
                "PBS directive; they would be silently dropped. Only "
                "'filesystems' (e.g. \"home\", \"eagle\", \"home:eagle\") is "
                "read — set other scheduler options in the script itself or "
                "leave custom_attributes empty."
            )
        raw = (attrs.custom_attributes.get("filesystems")
               or self._default_filesystems())
        tokens = [t for t in raw.split(":") if t]
        bad = [t for t in tokens if t not in _KNOWN_FILESYSTEMS]
        if bad or not tokens:
            raise ValueError(
                f"Invalid filesystems value {raw!r}. Crux jobs may name only "
                f"{', '.join(sorted(_KNOWN_FILESYSTEMS))} (colon-separated), "
                "and the value is written straight into #PBS -l filesystems. "
                "Set custom_attributes.filesystems accordingly or leave it "
                "unset for the default home:eagle."
            )
        return ":".join(tokens), tokens

    def validate_spec(self, spec: JobSpec) -> None:
        """Raise ValueError for anything Crux's PBS would reject confusingly
        — or accept and then silently drop, which on a routing queue is the
        worse failure (see the module docstring's routing-queue trap)."""
        attrs, res = spec.attributes, spec.resources

        queue, reservation = attrs.queue_name, attrs.reservation_id
        if reservation:
            if not _QUEUE_RE.fullmatch(reservation):
                raise ValueError(
                    f"Invalid reservation queue {reservation!r}. A Crux "
                    "reservation is a queue name (see pbs_rstat) rendered "
                    "into #PBS -q, so it must be a single token of letters, "
                    "digits, dot, underscore or hyphen — anything else would "
                    "inject extra options into the directive."
                )
            if queue and queue != reservation:
                raise ValueError(
                    f"Both queue_name ({queue!r}) and reservation_id "
                    f"({reservation!r}) are set. On Crux a reservation IS a "
                    "queue: pass only reservation_id (the backend renders "
                    "it as #PBS -q), or queue_name alone for a production "
                    "queue — never two different names."
                )
            queue = reservation
        elif queue:
            if not _QUEUE_RE.fullmatch(queue):
                raise ValueError(
                    f"Invalid queue name {queue!r}. It is written into "
                    "#PBS -q, so it must be a single token of letters, "
                    "digits, dot, underscore or hyphen — anything else would "
                    "inject extra options into the directive."
                )
            if queue not in self._queue_limits():
                known = ", ".join(sorted(self._queue_limits()))
                raise ValueError(
                    f"Unrecognised Crux queue {queue!r}. Known queues: "
                    f"{known}. If this is a reservation's queue name, pass "
                    "it as attributes.reservation_id instead (confirm it "
                    "with pbs_rstat first). Use get_facility or search_docs "
                    "rather than guessing a queue name."
                )
        else:
            raise ValueError(
                "Crux needs a queue: spec.attributes.queue_name is empty. "
                "Use 'debug' for short tests, 'workq-route' for production "
                "(or 'preemptable'/'demand' when you accept their terms), "
                "or attributes.reservation_id for a reservation queue."
            )

        if not attrs.account:
            raise ValueError(
                "Crux requires spec.attributes.account (the ALCF project to "
                "bill, rendered as #PBS -A — qsub refuses the job without "
                "one). Set it explicitly or let apply_defaults load your "
                "configured default."
            )
        if not _ACCOUNT_RE.fullmatch(attrs.account):
            raise ValueError(
                f"Invalid ALCF project {attrs.account!r}. Project names are "
                "alphanumeric with optional dot/underscore/hyphen (e.g. "
                "'Catalyst'). The value is written into the #PBS -A "
                "directive, so anything else could inject scheduler options."
            )

        if res.gpus or res.gpu_cores_per_process:
            raise ValueError(
                "Crux has no GPUs — it is a CPU-only AMD Rome system, so "
                "resources.gpus/gpu_cores_per_process must stay unset. "
                "CPU parallelism comes from node_count plus your mpiexec "
                "launch line (see the bundled guide's MPI section)."
            )
        if spec.container:
            raise ValueError(
                "Containers are not supported on Crux yet — ALCF has "
                "announced Apptainer support but it was not available at "
                "port time. Run natively (module-based environments, or a "
                "python venv) and drop spec.container."
            )
        if res.memory is not None and res.memory > self._node_memory_gib() * 1024**3:
            raise ValueError(
                f"Crux nodes have {self._node_memory_gib()} GiB and are "
                f"allocated whole, so a memory request of {res.memory} bytes "
                "can never run. Reduce it, or leave it unset — every job "
                "gets the node's full memory either way."
            )
        if ("processes_per_node" in res.model_fields_set
                and res.processes_per_node > self._max_threads_per_node()):
            raise ValueError(
                f"Crux nodes expose {self._max_threads_per_node()} hardware "
                f"threads, so processes_per_node={res.processes_per_node} "
                "cannot be placed. Rank placement is done by mpiexec at "
                "launch (--ppn), not by PBS — see the bundled guide."
            )
        if spec.stdin_path:
            raise ValueError(
                "Crux jobs have no mapped stdin directive; leave stdin_path "
                "unset and read input files explicitly in the executable."
            )

        self._filesystems_of(attrs)  # raises on anything not renderable

        limits = self._queue_limits().get(queue)
        if limits:
            nodes = res.node_count
            if not limits["min_nodes"] <= nodes <= limits["max_nodes"]:
                raise ValueError(
                    f"Crux queue {queue!r} allows "
                    f"{limits['min_nodes']}-{limits['max_nodes']} nodes, but "
                    f"{nodes} were requested. A job outside the range is "
                    "accepted by the routing queue and then dropped silently "
                    "— fix the node count or the queue."
                )
            walltime = _duration_seconds(attrs.duration)
            min_wt = limits["min_walltime_min"] * 60
            max_wt = limits["max_walltime_min"] * 60
            if not min_wt <= walltime <= max_wt:
                raise ValueError(
                    f"Crux queue {queue!r} allows walltimes of "
                    f"{limits['min_walltime_min']} min to "
                    f"{limits['max_walltime_min']} min, but the request is "
                    f"{_walltime(attrs.duration)}. A job outside the range "
                    "is accepted by the routing queue and then dropped "
                    "silently — fix attributes.duration or the queue."
                )

    # --- rendering -------------------------------------------------------

    def _header(self, spec: JobSpec) -> list[str]:
        """The #PBS directive block, in the documented ALCF shape. Calls
        validate_spec so a directly-rendered script is as safe as a
        submitted one."""
        attrs, res = spec.attributes, spec.resources
        self.validate_spec(spec)
        queue = attrs.reservation_id or attrs.queue_name
        filesystems, _ = self._filesystems_of(attrs)
        lines = [
            "#!/bin/bash -l",
            f"#PBS -N {spec.name}",
            f"#PBS -q {queue}",
            f"#PBS -A {attrs.account}",
            f"#PBS -l select={res.node_count}:system=crux",
            "#PBS -l place=scatter",
            f"#PBS -l walltime={_walltime(attrs.duration)}",
            f"#PBS -l filesystems={filesystems}",
            "#PBS -k doe",
        ]
        if queue == "preemptable":
            # ALCF: jobs in the preemptable queue can be killed whenever a
            # demand job needs the nodes; -r y asks PBS to rerun the job
            # from the start once that happens. Rendered automatically —
            # losing a 72-hour run silently is the failure this prevents.
            lines.append("#PBS -r y")
        if spec.stdout_path:
            lines.append(f"#PBS -o {shlex.quote(self._output_path(spec.stdout_path))}")
        if spec.stderr_path:
            lines.append(f"#PBS -e {shlex.quote(self._output_path(spec.stderr_path))}")
        return lines

    @staticmethod
    def _output_path(path: str) -> str:
        """Anchor an -o/-e destination at $HOME.

        qsub runs from the job script's directory (see submit()), and PBS
        resolves a relative -o/-e path against that directory. Every other
        tool here anchors relative paths at $HOME, so a leading '../' is
        added to keep both readings in agreement: '../x' from ~/agent/jobs
        is ~/x, exactly the $HOME-relative meaning the caller intended.
        Absolute paths pass through untouched.
        """
        normalized = norm_path(path)
        if normalized.startswith("/"):
            return normalized
        return "../" + normalized

    @staticmethod
    def _cd_line(directory: str | None) -> str:
        """Where the script body starts. With no spec.directory the job runs
        where qsub ran (~/agent/jobs, next to its output); an explicit
        directory is always $HOME-anchored when relative, for the same
        reason as _output_path."""
        if directory is None:
            return 'cd "$PBS_O_WORKDIR"'
        normalized = norm_path(directory)
        if normalized == ".":
            return 'cd "$HOME"'
        if normalized.startswith("/"):
            return f"cd {shlex.quote(normalized)}"
        return 'cd "$HOME"/' + shlex.quote(normalized)

    def render_script(self, spec: JobSpec) -> str:
        """JobSpec -> a #PBS batch script. Whole nodes only; rank placement
        is the launcher's job (mpiexec --ppn/--cpu-bind), so no process
        fields are rendered into directives."""
        lines = self._header(spec) + ["", self._cd_line(spec.directory)]
        return "\n".join(lines) + "\n" + render_body(
            spec, gpu_requested=False, gpu_vendor_flag="")

    # --- submission ------------------------------------------------------

    def submit(self, spec: JobSpec) -> dict:
        """Write the script under ~/agent/jobs and qsub it from there.

        Running qsub from the script's own directory is deliberate: ALCF
        forces -k doe, which streams output to the directory qsub ran in,
        so this keeps a job's stdout/stderr beside its script instead of
        loose in the home root (PORTING.md §10's visible-directory bias).
        """
        script = self.render_script(spec)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = write_remote_file(
            self.facility,
            f"{self._jobs_dir}/{spec.name}-{stamp}.pbs",
            script,
        )
        quoted = shlex.quote(path)
        # 600: the script may carry spec.environment exports, so keep it
        # owner-only; qsub only reads it, no execute bit needed.
        output = run_command(
            self.facility,
            f'chmod 600 {quoted} && cd "$(dirname {quoted})" && qsub {quoted}',
        )
        job_id = output.strip().splitlines()[-1].strip() if output.strip() else ""
        if not re.fullmatch(r"\d+\.\S+", job_id):
            raise RuntimeError(f"qsub did not return a PBS job ID: {output!r}")
        return {"job_id": job_id, "script_path": path}

    # --- status ----------------------------------------------------------

    @staticmethod
    def _pbs_workdir(variable_list: str) -> str:
        """Extract PBS_O_WORKDIR from qstat's Variable_List attribute."""
        for entry in variable_list.split(","):
            key, separator, value = entry.partition("=")
            if separator and key == "PBS_O_WORKDIR":
                return value
        return ""

    @staticmethod
    def _strip_host(path: str) -> str:
        """qstat reports Output_Path/Error_Path as [<hostname>:]<path>; drop
        the hostname so the remainder is a path usable on the filesystem."""
        if path.startswith("/"):
            return path
        _, separator, rest = path.partition(":")
        return rest if separator else path

    @classmethod
    def _workdir_of(cls, fields: dict) -> str:
        """The job's submission directory — where its output files land.

        PBS_O_WORKDIR from Variable_List is the direct answer, but history
        records of finished jobs carry no Variable_List at all (confirmed
        live); Output_Path is set at submit time in every record, so its
        directory is the fallback that keeps workdir working after a job
        finishes — exactly when the output is worth reading.
        """
        workdir = cls._pbs_workdir(_attr(fields, "Variable_List"))
        if workdir:
            return workdir
        output_path = cls._strip_host(_attr(fields, "Output_Path"))
        if output_path:
            return posixpath.dirname(output_path) or "."
        return ""

    @classmethod
    def _job(cls, job_id: str, fields: dict) -> Job:
        """One qstat -F JSON record -> the shared Job model."""
        native = _attr(fields, "job_state")
        state = _PBS_STATES.get(native, JobState.UNKNOWN)
        comment = _attr(fields, "comment")
        exit_code = None
        raw_exit = _attr(fields, "Exit_status")
        if raw_exit:
            try:
                exit_code = int(raw_exit)
            except ValueError:
                exit_code = None
        message = comment or _attr(fields, "queue") or None
        if native in ("F", "X"):
            if _SCHEDULER_DELETE_MARKER in comment.lower():
                # Preemption (or admin deletion): the scheduler killed it.
                # Deliberately FAILED, not CANCELED — the user didn't stop
                # it, and IRI has no "preempted" state; the comment explains.
                state = JobState.FAILED
            elif exit_code not in (None, 0):
                state = JobState.FAILED
        return Job(
            id=job_id,
            status=JobStatus(
                state=state,
                exit_code=exit_code,
                message=message,
                meta_data={
                    "scheduler": "pbs",
                    "native_state": native,
                    "queue": _attr(fields, "queue"),
                    "job_name": _attr(fields, "Job_Name"),
                    "account": _attr(fields, "Account_Name"),
                    "walltime_used": _attr(fields, "resources_used.walltime"),
                    "exec_host": _attr(fields, "exec_host"),
                    "workdir": cls._workdir_of(fields),
                    "output_path": cls._strip_host(
                        _attr(fields, "Output_Path")),
                    "error_path": cls._strip_host(
                        _attr(fields, "Error_Path")),
                },
            ),
        )

    @staticmethod
    def _parse_qstat_json(output: str) -> dict[str, dict]:
        """`qstat -fx -F JSON` output -> {full job id: attribute dict}."""
        if not output.strip():
            return {}
        payload = json.loads(output)
        jobs = payload.get("Jobs", {})
        return jobs if isinstance(jobs, dict) else {}

    def _status_of(self, job_id: str) -> Job:
        """Full record for one id via `qstat -fx -F JSON <id>`.

        -x reaches finished jobs too (ALCF keeps ~two weeks), and JSON
        output has no fixed-width truncation to work around. The bare
        sequence number is accepted as an id everywhere, matching what
        list views report.
        """
        try:
            output = run_command(
                self.facility,
                f"qstat -fx -F JSON {shlex.quote(job_id)}",
            )
        except RuntimeError as exc:
            return Job(id=job_id, status=JobStatus(
                state=JobState.UNKNOWN,
                message=(
                    f"{job_id} was not found by qstat (including its "
                    "finished-job history): " + str(exc) + ". ALCF keeps "
                    "about two weeks of history, and a job that fit no "
                    "execution queue after routing never appears at all — "
                    "check its node count and walltime against "
                    "get_facility's queue limits."
                ),
                meta_data={"scheduler": "pbs"},
            ))
        for full_id, fields in self._parse_qstat_json(output).items():
            if full_id == job_id or _sequence_of(full_id) == _sequence_of(job_id):
                return self._job(full_id, fields)
        return Job(id=job_id, status=JobStatus(
            state=JobState.UNKNOWN,
            message=(
                f"{job_id} was accepted by qstat but returned no record. "
                "If it was submitted to workq-route, it may have been "
                "dropped after routing (a known PBS behaviour): compare its "
                "node count and walltime with get_facility's queue limits."
            ),
            meta_data={"scheduler": "pbs"},
        ))

    def get_statuses(self, job_ids: list[str]) -> list[Job]:
        """One qstat call per id: a missing id must not fail its siblings,
        and each miss needs its own explanation."""
        return [self._status_of(job_id) for job_id in job_ids]

    def get_recent_statuses(self, since: str = "now-2days") -> list[Job]:
        """The user's jobs (live and finished) created in the last N days.

        Two steps, both documented PBS Professional shapes: `qselect -x -u
        $USER -tc.gt.<CCYYMMDDhhmm>` lists matching ids with no truncation
        (and `-x` includes finished jobs), then full records come from
        `qstat -fx -F JSON` in small batches to stay under the middleware's
        per-call output cap. `since` is capped at 14 days — ALCF's history
        window — and anything unparseable falls back to two days.
        """
        days = 2
        if match := re.fullmatch(r"now-(\d+)days?", since):
            days = min(14, max(1, int(match.group(1))))
        cutoff = time.strftime(
            "%Y%m%d%H%M", time.gmtime(time.time() - days * 86400))
        output = run_command(
            self.facility,
            f"qselect -x -u $USER -tc.gt.{cutoff}",
        )
        ids = [line.strip() for line in output.splitlines() if line.strip()]
        jobs: list[Job] = []
        for start in range(0, len(ids), _QSTAT_BATCH):
            batch = " ".join(shlex.quote(i) for i in ids[start:start + _QSTAT_BATCH])
            records = self._parse_qstat_json(
                run_command(self.facility, f"qstat -fx -F JSON {batch}")
            )
            jobs.extend(self._job(full_id, fields)
                        for full_id, fields in records.items())
        return jobs

    def cancel(self, job_id: str) -> Job | str:
        """qdel; the deletion is what the caller asked for, so success is
        reported as CANCELED even though PBS takes a moment to finish the
        job (it re-reads as `failed` with a deletion comment if polled)."""
        run_command(self.facility, f"qdel {shlex.quote(job_id)}")
        return Job(id=job_id, status=JobStatus(
            state=JobState.CANCELED,
            message=f"qdel {job_id} accepted; poll get_job_status to watch "
                    "the job reach a finished state.",
            meta_data={"scheduler": "pbs"},
        ))

    # --- update ----------------------------------------------------------

    def update(self, job_id: str, spec: JobSpec) -> Job:
        """Apply a JobSpec to a queued (or, for walltime, running) job.

        PBS Professional splits the verbs: `qalter` changes name, walltime,
        project, and resource requests, while moving between queues is
        `qmove` — there is no -q on qalter. Only fields the caller actually
        set are applied; everything else they set is reported back as not
        applied rather than silently dropped (the same contract as
        SlurmBackend.update, and for the same reason: a JobSpec carries
        defaults that must not masquerade as requests).
        """
        assignments: list[str] = []
        unsupported: list[str] = []

        top_level = spec.model_fields_set
        if "name" in top_level:
            assignments.append(f"-N {shlex.quote(spec.name)}")
        if "stdout_path" in top_level:
            # qalter resolves a relative -o/-e against its own working
            # directory, which here is $HOME (run_command always cds there),
            # so this uses the plain $HOME-relative form — no '../' prefix,
            # unlike the render path where qsub runs from the jobs directory.
            assignments.append(
                f"-o {shlex.quote(norm_path(spec.stdout_path))}")
        if "stderr_path" in top_level:
            assignments.append(
                f"-e {shlex.quote(norm_path(spec.stderr_path))}")
        unsupported += sorted(top_level - {"name", "resources", "attributes",
                                           "executable", "stdout_path",
                                           "stderr_path"})

        attr_set = spec.attributes.model_fields_set
        if "duration" in attr_set:
            assignments.append(f"-l walltime={_walltime(spec.attributes.duration)}")
        if "account" in attr_set and spec.attributes.account:
            if not _ACCOUNT_RE.fullmatch(spec.attributes.account):
                raise ValueError(
                    f"Invalid ALCF project {spec.attributes.account!r} — the "
                    "same identifier rules apply to qalter -A as to #PBS -A."
                )
            assignments.append(f"-A {shlex.quote(spec.attributes.account)}")
        unsupported += [f"attributes.{f}" for f in
                        sorted(attr_set - {"duration", "account",
                                           "queue_name", "reservation_id"})]

        res_set = spec.resources.model_fields_set
        if "node_count" in res_set:
            assignments.append(
                f"-l select={int(spec.resources.node_count)}:system=crux")
        unsupported += [f"resources.{f}" for f in sorted(res_set - {"node_count"})]

        move_to = None
        for field in ("queue_name", "reservation_id"):
            if field in attr_set and getattr(spec.attributes, field):
                candidate = getattr(spec.attributes, field)
                if not _QUEUE_RE.fullmatch(candidate):
                    raise ValueError(
                        f"Invalid queue {candidate!r} — it is passed to qmove "
                        "as a single token, so only letters, digits, dot, "
                        "underscore and hyphen are safe."
                    )
                if move_to and move_to != candidate:
                    raise ValueError(
                        f"queue_name ({spec.attributes.queue_name!r}) and "
                        f"reservation_id ({spec.attributes.reservation_id!r}) "
                        "name different queues. On Crux a reservation IS a "
                        "queue — pass one or the other to update_job."
                    )
                move_to = candidate

        if not assignments and not move_to:
            raise ValueError(
                "Nothing updatable in this spec. On Crux, qalter can change "
                "the job name, walltime, project and node count, and qmove "
                "can change the queue; set one of those on the spec you pass."
                + (f" Ignored: {', '.join(unsupported)}." if unsupported else "")
            )

        if assignments:
            run_command(self.facility,
                        f"qalter {' '.join(assignments)} {shlex.quote(job_id)}")
        if move_to:
            run_command(self.facility,
                        f"qmove {shlex.quote(move_to)} {shlex.quote(job_id)}")
        jobs = self.get_statuses([job_id])
        job = jobs[0] if jobs else Job(id=job_id, status=JobStatus(
            state=JobState.UNKNOWN, meta_data={"scheduler": "pbs"}))
        if unsupported and job.status:
            note = ("Not applied (this scheduler cannot change these after "
                    "submission): " + ", ".join(unsupported))
            job.status.message = (f"{job.status.message} — {note}"
                                  if job.status.message else note)
        return job

    # --- live resources ----------------------------------------------------

    @staticmethod
    def _parse_qstat_Q(output: str) -> list[dict]:
        """`qstat -Q` default table -> per-queue job counts. Header-driven:
        the column set is read from the header line itself, so a PBS point
        release adding or dropping a column still parses."""
        rows: list[dict] = []
        columns: list[str] | None = None
        for line in output.splitlines():
            tokens = line.split()
            if not tokens:
                continue
            if columns is None:
                if tokens[0] == "Queue" and "Ena" in tokens and "Str" in tokens:
                    columns = tokens
                continue
            if set(tokens[0]) <= {"-"}:      # the ---- separator line
                continue
            if len(tokens) != len(columns):
                continue                    # totals/footer junk
            row = dict(zip(columns, tokens))
            rows.append(row)
        if not rows:
            raise ValueError(
                f"Could not parse qstat -Q output as a queue table: "
                f"{output[:200]!r}"
            )
        return rows

    @staticmethod
    def _parse_pbsnodes_table(output: str) -> dict[str, int]:
        """`pbsnodes -avSj` summary table -> node counts by category. On
        ALCF a vnode is a whole host (force_exclhost), so rows are nodes."""
        started = False
        counts = {"allocated": 0, "idle": 0, "other": 0, "total": 0}
        for line in output.splitlines():
            tokens = line.split()
            if not tokens:
                continue
            if not started:
                if tokens[0] == "vnode":
                    started = True        # header; rows follow the separator
                continue
            if set(tokens[0]) <= {"-"}:
                continue
            if len(tokens) < 2 or not re.fullmatch(r"[a-z][a-z,-]*", tokens[1]):
                continue                  # not a state row (footer/notes)
            counts["total"] += 1
            if tokens[1] == "free":
                counts["idle"] += 1
            elif tokens[1] == "job-exclusive":
                counts["allocated"] += 1
            else:                          # offline, resv-exclusive, down, ...
                counts["other"] += 1
        if not counts["total"]:
            raise ValueError(
                f"Could not parse pbsnodes -avSj output as a node table: "
                f"{output[:200]!r}"
            )
        return counts

    def get_live_resources(self) -> list[dict]:
        """Queue rows from `qstat -Q`, each carrying the machine-wide node
        pool from `pbsnodes -avSj`.

        Crux has one shared node pool — queues are policy (limits and
        priority), not separate hardware — so the same node counts attach to
        every queue row: idle nodes answer 'will a job start soon' no matter
        which queue you target. Counts are job-level per queue.
        """
        def count(row: dict, key: str) -> int:
            try:
                return int(row.get(key, "0"))
            except ValueError:
                return 0            # e.g. a "--" placeholder; not an error

        queue_rows = self._parse_qstat_Q(run_command(self.facility, "qstat -Q"))
        nodes = self._parse_pbsnodes_table(
            run_command(self.facility, "pbsnodes -avSj"))
        partitions = []
        for row in queue_rows:
            partitions.append({
                "partition": row["Queue"],
                # qstat -Q truncates display values with a trailing '*' when
                # a column is narrow (seen live: "Exe*"/"Rou*") — strip it.
                "queue_type": row.get("Type", "").rstrip("*"),
                "enabled": row.get("Ena", ""),
                "started": row.get("Str", ""),
                "queued_jobs": count(row, "Que"),
                "running_jobs": count(row, "Run"),
                "held_jobs": count(row, "Hld"),
                "total_jobs": count(row, "Tot"),
                "nodes": dict(nodes),
            })
        return partitions

    def get_drained_nodes(self) -> list[dict]:
        """`pbsnodes -l`: nodes that are down, with PBS's own explanation."""
        output = run_command(self.facility, "pbsnodes -l")
        drained = []
        for line in output.splitlines():
            tokens = line.split(None, 1)
            if len(tokens) == 2:
                state, _, reason = tokens[1].partition(" ")
                drained.append({
                    "nodes": tokens[0],
                    "state": state,
                    "reason": reason.strip(),
                })
        return drained

    # --- accounting (sbank) ------------------------------------------------

    @staticmethod
    def _parse_sbank_rows(output: str) -> list[dict[str, str]]:
        """Body rows of a sbank list command.

        sbank prints a two-line header, dash separators, data rows, then a
        Totals block; the Totals section is left out. Rows are recognized
        structurally (leading integer id), so this works for the different
        column sets of sbank-list-allocations and sbank-list-jobs alike —
        callers pick fields out positionally, from both ends, because
        project names may contain spaces.
        """
        rows: list[dict[str, str]] = []
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped or set(stripped) <= {"-"}:
                continue
            if stripped.startswith(("Totals:", "Date filters")):
                break
            tokens = stripped.split()
            if len(tokens) < 8 or not tokens[0].isdigit():
                continue    # column-header line or unexpected prose
            rows.append({
                "tokens": tokens,
                "id": tokens[0],
            })
        return rows

    def _allocations(self) -> list[dict]:
        """The user's Crux allocations via sbank-list-allocations, with the
        numeric columns already converted (sbank prints thousands
        separators; balances may be negative).

        ALCF's sbank adds a Suballocation column to the documented default
        layout, so the leading columns are located by shape — the start/end
        date pair — rather than by fixed position. Rows are additionally
        filtered to resource 'crux' so a site whose -r filter ever loosens
        can't leak another machine's allocations into Crux results.
        """
        output = run_command(self.facility, "sbank-list-allocations -r crux")

        def number(token: str) -> float:
            return float(token.replace(",", ""))

        rows = []
        for row in self._parse_sbank_rows(output):
            tokens = row["tokens"]
            # Jobs, Charged, Available Balance are the last three fields;
            # the project name may contain spaces and is whatever sits
            # between the fixed leading fields and those.
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", tokens[3]):
                # ALCF layout: Allocation Suballocation Start End Resource...
                allocation_id, start, end, resource = (
                    tokens[0], tokens[2], tokens[3], tokens[4])
                project = " ".join(tokens[5:-3])
                suballocation_id = tokens[1]
            else:
                # sbank's default layout: Id Start End Resource...
                allocation_id, start, end, resource = (
                    tokens[0], tokens[1], tokens[2], tokens[3])
                project = " ".join(tokens[4:-3])
                suballocation_id = None
            if resource.lower() != "crux":
                continue
            rows.append({
                "allocation_id": allocation_id,
                "suballocation_id": suballocation_id,
                "start": start,
                "end": end,
                "resource": resource,
                "project": project,
                "jobs": int(tokens[-3].replace(",", "")),
                "charged": number(tokens[-2]),
                "available_balance": number(tokens[-1]),
            })
        return rows

    def get_projects(self) -> list[dict]:
        """The user's chargeable ALCF projects on Crux, with sbank balances.

        `account` is exactly the string for #PBS -A. Raises when sbank
        reports no rows: an ALCF account always belongs to at least one
        project, so an empty result means the allocation expired (renew via
        MyALCF) or sbank is unavailable — either is actionable, and an
        empty list here would read as 'no projects' when it never is.
        """
        allocations = self._allocations()
        if not allocations:
            raise ValueError(
                "sbank-list-allocations returned no active allocations for "
                "resource 'crux'. Either your project's allocation has "
                "expired (renew at my.alcf.anl.gov) or the sbank view is "
                "unavailable — run `sbank-list-allocations -r all` to check "
                "the resource name and your projects' dates."
            )
        projects: dict[str, dict] = {}
        for alloc in allocations:
            entry = projects.setdefault(alloc["project"], {
                "account": alloc["project"],
                "resource": "crux",
                "allocation_ids": [],
                "jobs": 0,
                "charged": 0.0,
                "available_balance": 0.0,
            })
            entry["allocation_ids"].append(alloc["allocation_id"])
            entry["jobs"] += alloc["jobs"]
            entry["charged"] += alloc["charged"]
            entry["available_balance"] += alloc["available_balance"]
        return [projects[name] for name in sorted(projects)]

    def get_project_allocations(self, project_id: str) -> dict:
        """A project's Crux allocations: window, jobs, charged, and what's
        left, per allocation and in total (node-hours from sbank)."""
        rows = [a for a in self._allocations() if a["project"] == project_id]
        if not rows:
            raise ValueError(
                f"No Crux allocations found for project {project_id!r}. "
                "Call get_projects to see the projects you may charge."
            )
        return {
            "project_id": project_id,
            "resource": "crux",
            "allocations": rows,
            "charged_total": sum(a["charged"] for a in rows),
            "available_balance_total": sum(
                a["available_balance"] for a in rows),
        }

    def get_user_allocations(self, project_id: str) -> dict:
        """The current user's charged usage inside one project, from
        sbank-list-jobs (their node-hours and job count on Crux)."""
        output = run_command(
            self.facility,
            f"sbank-list-jobs -u $USER -p {shlex.quote(project_id)} -r crux",
        )
        jobs = []
        charged = 0.0
        for row in self._parse_sbank_rows(output):
            tokens = row["tokens"]
            # Id Jobid Resource <Project...> Allocation User Duration Charged
            jobs.append(tokens[1])
            try:
                charged += float(tokens[-1].replace(",", ""))
            except ValueError:
                pass
        return {
            "project_id": project_id,
            "resource": "crux",
            "jobs": len(jobs),
            "job_ids": jobs,
            "charged_total": charged,
        }

    # --- health -----------------------------------------------------------

    def check_scheduler(self) -> bool:
        """Three signals: the client tools exist on PATH, `qstat --version`
        names PBS itself (the doctor's standard version probe — seen live it
        prints `pbs_version = 2026.1.0...`), and `qstat -Q` proves the PBS
        server actually answers with a queue table, which a version flag
        alone never touches.
        """
        from hpc_agent_core.doctor import (
            FAIL,
            check_commands_on_path,
            check_ssh_scheduler_probe,
        )
        tools_ok = check_commands_on_path(
            self.facility,
            ["qsub", "qstat", "qdel", "qalter", "qselect", "pbsnodes",
             "sbank-list-allocations"],
            "pbs",
        )
        version_ok = check_ssh_scheduler_probe(
            self.facility, "qstat --version", "pbs")
        try:
            output = run_command(self.facility, "qstat -Q")
        except RuntimeError as exc:
            print(f"{FAIL} pbs server: qstat -Q failed: {exc}")
            return False
        if "Queue" not in output:
            print(f"{FAIL} pbs server: qstat -Q did not return a queue "
                  f"table: {output[:200]}")
            return False
        print("\u2713 pbs server: qstat -Q answered with the queue table")
        return tools_ok and version_ok
