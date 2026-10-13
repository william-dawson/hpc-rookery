"""PBS Professional backend for Miyabi.

The command shapes and parsers were carried over from Miyabi-Agent, where
they were exercised on the live machine on 2026-07-13.  They are local to
this facility because no second PBS facility has established a genuinely
shared dialect yet, and Miyabi's qstat wrappers are site-specific.
"""
from __future__ import annotations

import math
import re
import shlex
import time

from hpc_agent_core.compute.base import SchedulerBackend, duration_to_hms, render_body
from hpc_agent_core.middleware import run_command, write_remote_file
from hpc_agent_core.models import Job, JobSpec, JobState, JobStatus


_PBS_STATES = {
    "T": JobState.QUEUED,       # transit
    "Q": JobState.QUEUED,
    "W": JobState.QUEUED,       # waiting for execution time
    "H": JobState.HELD,
    "S": JobState.HELD,         # suspended
    "R": JobState.ACTIVE,
    "E": JobState.ACTIVE,       # exiting
    "B": JobState.ACTIVE,       # array job begun
    "F": JobState.COMPLETED,
    "X": JobState.COMPLETED,    # finished/expired subjob
}

_HISTORY_STATES = {"FINISH": JobState.COMPLETED}
#: PBS group_list identifiers seen at JCAHPC are alphanumeric with optional
#: separators (e.g. "jh210022"). Anything else is rejected rather than
#: rendered: attrs.account is interpolated straight into a `#PBS -W` line,
#: where a space would append further scheduler options to that directive.
_GROUP_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")

#: Same reasoning for the queue, which lands in `#PBS -q`. A prefix check
#: used to guard this, which let "debug-c -l place=excl" through — it starts
#: with "debug-" and then injects an extra option into the directive.
#: The exact set lives in the bundled facts, so it stays right as queues
#: change instead of drifting from a hardcoded tuple.
def _known_queues(facility: str) -> frozenset[str]:
    from hpc_agent_core import config as _config
    queues = _config.load_facts(facility).get("queues", {})
    names: set[str] = set()
    for value in queues.values():
        if isinstance(value, list):          # skip the "note" string entry
            names.update(str(v) for v in value)
    return frozenset(names)


class PBSBackend(SchedulerBackend):
    def __init__(self, facility: str, jobs_dir: str = "agent/jobs"):
        super().__init__(facility=facility, name="pbs")
        self._jobs_dir = jobs_dir

    @staticmethod
    def _is_gpu_queue(queue: str) -> bool:
        return queue.endswith("-g") or queue.endswith("-mig") or "-mig" in queue

    @staticmethod
    def _is_mig_queue(queue: str) -> bool:
        return queue.endswith("-mig") or "-mig" in queue

    @staticmethod
    def _cpu_cores_per_chunk(queue: str) -> int | None:
        """Return the dated hardware limit for the selected queue family.

        These are physical CPU cores exposed by the configurations that were
        live-tested in Miyabi-Agent on 2026-07-13.  ``prepost`` is omitted:
        its current shape was not established strongly enough to reject a job
        offline, so users must inspect that queue live.
        """
        if queue.endswith("-c"):
            return 112
        if queue.endswith("-g"):
            return 72
        if queue.endswith("-mig") or "-mig" in queue:
            return 18
        return None

    @staticmethod
    def _memory_gib(memory_bytes: int | None) -> str | None:
        return None if memory_bytes is None else f"{math.ceil(memory_bytes / 1024**3)}gb"

    @staticmethod
    def _processes_per_chunk(spec: JobSpec) -> int:
        """Resolve PSI/J's alternative total-process representation for PBS."""
        res = spec.resources
        if res.process_count is None:
            return res.processes_per_node
        if "processes_per_node" in res.model_fields_set:
            expected = res.node_count * res.processes_per_node
            if res.process_count != expected:
                raise ValueError(
                    "Miyabi received both process_count and processes_per_node, "
                    f"but {res.process_count} != node_count({res.node_count}) x "
                    f"processes_per_node({res.processes_per_node}). Make them "
                    "consistent or set only one process shape."
                )
            return res.processes_per_node
        quotient, remainder = divmod(res.process_count, res.node_count)
        if remainder:
            raise ValueError(
                f"Miyabi cannot spread process_count={res.process_count} evenly "
                f"over node_count={res.node_count}. Set processes_per_node "
                "explicitly or choose a divisible total."
            )
        return quotient

    def validate_spec(self, spec: JobSpec) -> None:
        attrs, res = spec.attributes, spec.resources
        queue = attrs.queue_name
        if not queue:
            raise ValueError(
                "Miyabi requires spec.attributes.queue_name. Use get_resources "
                "to choose a current CPU (-c), full-GPU (-g), or MIG (-mig) queue."
            )
        known = _known_queues(self.facility)
        if queue not in known:
            raise ValueError(
                f"Unrecognised Miyabi queue {queue!r}. Known queues: "
                f"{', '.join(sorted(known))}. Use get_resources or search_docs "
                "rather than guessing a PBS queue name. (The name must match "
                "exactly — it is written into the #PBS -q directive, so a "
                "value carrying extra text would inject scheduler options.)"
            )
        if not attrs.account:
            raise ValueError(
                "Miyabi requires spec.attributes.account (the PBS group_list project). "
                "Set it explicitly or let apply_defaults load your configured group."
            )
        if not _GROUP_RE.fullmatch(attrs.account):
            raise ValueError(
                f"Invalid Miyabi project group {attrs.account!r}. A PBS "
                "group_list identifier is alphanumeric, optionally with _ or "
                "-, e.g. 'jh210022'. It is written into the #PBS -W directive, "
                "so a value carrying extra text would inject scheduler options."
            )

        ppn = self._processes_per_chunk(spec)
        cpu_limit = self._cpu_cores_per_chunk(queue)
        requested_cores = ppn * (res.cpu_cores_per_process or 1)
        if cpu_limit is not None and requested_cores > cpu_limit:
            raise ValueError(
                f"Miyabi queue {queue!r} has a recorded limit of {cpu_limit} "
                f"CPU cores per select chunk, but this shape requests "
                f"{requested_cores}. Reduce processes_per_node/process_count "
                "or cpu_cores_per_process, then confirm the current limit with "
                "get_resources before submitting."
            )

        requested_gpus = res.gpus or res.gpu_cores_per_process or 0
        if requested_gpus:
            if not self._is_gpu_queue(queue):
                raise ValueError(
                    f"Miyabi queue {queue!r} is not a GPU queue. Use a -g or "
                    "-mig queue, or leave GPU fields unset for CPU work."
                )
            if requested_gpus != res.node_count:
                unit = "MIG instance" if self._is_mig_queue(queue) else "full GPU node"
                raise ValueError(
                    f"On Miyabi, queue selection allocates one {unit} per select "
                    f"chunk. resources.gpus ({requested_gpus}) must therefore equal "
                    f"node_count ({res.node_count}), or may be left at zero because "
                    "the PBS queue already determines the GPU allocation."
                )

        if attrs.reservation_id:
            raise ValueError(
                "Miyabi's verified PBS interface has no mapped reservation_id "
                "directive. Leave it unset or confirm the site-specific syntax first."
            )
        if attrs.custom_attributes:
            raise ValueError(
                "Miyabi custom PBS attributes are not mapped by this backend. "
                "Leave custom_attributes empty rather than silently dropping them."
            )
        if res.exclusive_node_use:
            raise ValueError(
                "Miyabi exclusive_node_use has no separately verified PBS "
                "directive in this port. Leave it false; queue/select semantics "
                "already determine the allocation, or verify the current site "
                "syntax before adding support."
            )
        if spec.stdin_path:
            raise ValueError(
                "Miyabi stdin_path has not been verified against its PBS wrapper; "
                "leave it unset and read input explicitly in the executable."
            )

    def _header(self, spec: JobSpec) -> list[str]:
        attrs, res = spec.attributes, spec.resources
        self.validate_spec(spec)  # rendered scripts must be safe in isolation too
        ppn = self._processes_per_chunk(spec)
        select = f"select={res.node_count}:mpiprocs={ppn}"
        if res.cpu_cores_per_process:
            select += f":ompthreads={res.cpu_cores_per_process}"
        if memory := self._memory_gib(res.memory):
            select += f":mem={memory}"

        lines = [
            "#!/bin/bash",
            f"#PBS -N {spec.name}",
            f"#PBS -q {attrs.queue_name}",
            f"#PBS -W group_list={attrs.account}",
            f"#PBS -l {select}",
            f"#PBS -l walltime={duration_to_hms(attrs.duration)}",
        ]
        # Output paths are quoted: a path containing a space would otherwise
        # split into a second argument on the directive line, which PBS reads
        # as another option rather than part of the filename.
        if spec.stdout_path and spec.stderr_path:
            lines.extend([f"#PBS -o {shlex.quote(spec.stdout_path)}",
                          f"#PBS -e {shlex.quote(spec.stderr_path)}"])
        elif spec.stderr_path:
            lines.extend(["#PBS -j eo", f"#PBS -e {shlex.quote(spec.stderr_path)}"])
        else:
            lines.append("#PBS -j oe")
            if spec.stdout_path:
                lines.append(f"#PBS -o {shlex.quote(spec.stdout_path)}")
        return lines

    @staticmethod
    def _cd_line(directory: str | None) -> str:
        if directory is None:
            return 'cd "$PBS_O_WORKDIR"'
        if directory == "~":
            return 'cd "$HOME"'
        if directory.startswith("~/"):
            return 'cd "$HOME"/' + shlex.quote(directory[2:])
        return f"cd {shlex.quote(directory)}"

    def render_script(self, spec: JobSpec) -> str:
        queue = spec.attributes.queue_name
        lines = self._header(spec) + ["", self._cd_line(spec.directory)]
        return "\n".join(lines) + "\n" + render_body(
            spec,
            gpu_requested=self._is_gpu_queue(queue),
            gpu_vendor_flag="--nv",
        )

    def submit(self, spec: JobSpec) -> dict:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = write_remote_file(
            self.facility,
            f"{self._jobs_dir}/{spec.name}-{stamp}.pbs",
            self.render_script(spec),
        )
        quoted = shlex.quote(path)
        output = run_command(self.facility, f"chmod 700 {quoted} && qsub {quoted}")
        job_id = output.strip().splitlines()[-1].strip() if output.strip() else ""
        if not re.fullmatch(r"\d+\.\S+", job_id):
            raise RuntimeError(f"qsub did not return a PBS job ID: {output!r}")
        return {"job_id": job_id, "script_path": path}

    @staticmethod
    def _parse_blocks(text: str) -> list[dict[str, str]]:
        blocks: list[dict[str, str]] = []
        current: dict[str, str] | None = None
        for line in text.splitlines():
            if line.startswith("Job Id:"):
                if current:
                    blocks.append(current)
                current = {"Job_Id": line.split(":", 1)[1].strip()}
            elif current and " = " in line:
                key, value = line.strip().split(" = ", 1)
                current[key] = value.strip()
        if current:
            blocks.append(current)
        return blocks

    @staticmethod
    def _pbs_workdir(variable_list: str) -> str:
        """Extract PBS's original submission directory from Variable_List."""
        for entry in variable_list.split(","):
            key, separator, value = entry.partition("=")
            if separator and key == "PBS_O_WORKDIR":
                return value
        return ""

    @staticmethod
    def _job(fields: dict[str, str]) -> Job:
        native = fields.get("job_state", "")
        state = _PBS_STATES.get(native, JobState.UNKNOWN)
        exit_code = None
        if native in ("F", "X") and "Exit_status" in fields:
            try:
                exit_code = int(fields["Exit_status"])
            except ValueError:
                exit_code = None
            if exit_code not in (None, 0):
                state = JobState.FAILED
        return Job(
            id=fields.get("Job_Id", ""),
            status=JobStatus(
                state=state,
                exit_code=exit_code,
                message=fields.get("comment") or fields.get("queue"),
                meta_data={
                    "scheduler": "pbs",
                    "native_state": native,
                    "queue": fields.get("queue", ""),
                    "job_name": fields.get("Job_Name", ""),
                    "resources_used_walltime": fields.get("resources_used.walltime", ""),
                    "exec_host": fields.get("exec_host", ""),
                    "workdir": PBSBackend._pbs_workdir(
                        fields.get("Variable_List", "")
                    ),
                },
            ),
        )

    @staticmethod
    def _parse_history(text: str) -> list[Job]:
        jobs: list[Job] = []
        for line in text.splitlines():
            fields = line.split()
            if len(fields) < 10 or not fields[0].isdigit():
                continue
            job_id, job_name, native, project, queue = fields[:5]
            jobs.append(Job(
                id=job_id,
                status=JobStatus(
                    state=_HISTORY_STATES.get(native, JobState.UNKNOWN),
                    message=(
                        "Miyabi history reports FINISH; application exit status "
                        "is unavailable here. Check output or tracejob."
                        if native == "FINISH" else None
                    ),
                    meta_data={
                        "scheduler": "pbs",
                        "native_state": native,
                        "job_name": job_name,
                        "project": project,
                        "queue": queue,
                        "start_date": " ".join(fields[5:7]),
                        "elapsed": fields[7],
                        "token": fields[8],
                        "nodes": fields[9],
                        "mig": fields[10] if len(fields) > 10 else "",
                    },
                ),
            ))
        return jobs

    def _optional(self, command: str) -> str:
        try:
            return run_command(self.facility, command)
        except RuntimeError:
            return ""

    def get_statuses(self, job_ids: list[str]) -> list[Job]:
        result: list[Job] = []
        for job_id in job_ids:
            fields = self._parse_blocks(
                self._optional(f"qstat -f {shlex.quote(job_id)}")
            )
            if fields:
                result.append(self._job(fields[0]))
                continue
            history_id = job_id.split(".", 1)[0]
            history = self._parse_history(
                self._optional(f"qstat -H {shlex.quote(history_id)}")
            )
            result.append(history[0] if history else Job(
                id=job_id,
                status=JobStatus(
                    state=JobState.UNKNOWN,
                    message="Job is absent from live qstat and Miyabi's short history window.",
                    meta_data={"scheduler": "pbs"},
                ),
            ))
        return result

    def get_recent_statuses(self, since: str = "now-2days") -> list[Job]:
        # Miyabi's wrapper owns filtering and retains at most three days.
        days = 2
        if match := re.fullmatch(r"now-(\d+)days?", since):
            days = min(3, max(1, int(match.group(1))))
        return self._parse_history(
            self._optional(f"qstat -H --hday {days} --hnum 100")
        )

    def cancel(self, job_id: str) -> Job | str:
        try:
            run_command(self.facility, f"qdel {shlex.quote(job_id)}")
        except RuntimeError as exc:
            return Job(id=job_id, status=JobStatus(
                state=JobState.UNKNOWN,
                message=str(exc),
                meta_data={"scheduler": "pbs"},
            ))
        return Job(id=job_id, status=JobStatus(
            state=JobState.CANCELED,
            message=f"qdel {job_id} succeeded",
            meta_data={"scheduler": "pbs"},
        ))

    def get_live_resources(self) -> list[dict]:
        """Parse Miyabi's site-specific ``qstat --rscuse`` table."""
        output = run_command(self.facility, "qstat --rscuse")
        system = ""
        kind = "node"
        rows: list[dict] = []
        pattern = re.compile(r"^(\S.*?)\s+[*-]+\s+(\d+)%\s+(\d+)\/\s*(\d+)\s*$")
        for line in output.splitlines():
            if line.startswith("SYSTEM:"):
                system = line.split(":", 1)[1].strip()
            elif "Total(MIG)" in line:
                kind = "mig"
            elif "Total(Node)" in line:
                kind = "node"
            elif match := pattern.match(line):
                queue, ratio, used, total = match.groups()
                rows.append({
                    "partition": queue.strip(),
                    "system": system,
                    "kind": kind,
                    "used": int(used),
                    "total": int(total),
                    "available": int(total) - int(used),
                    "used_percent": int(ratio),
                })
        return rows

    def check_scheduler(self) -> bool:
        from hpc_agent_core.doctor import check_commands_on_path
        return check_commands_on_path(
            self.facility,
            ["qsub", "qstat", "qdel", "tracejob", "show_quota", "show_token"],
            "pbs",
        )
