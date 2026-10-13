"""TSUBAME4's resource-type Altair Grid Engine dialect.

TSUBAME jobs request fixed slices (``-l node_f=2``, ``-l gpu_1=1``), not a
generic node/slot shape.  That makes the shared slot-oriented Grid Engine
backend the wrong abstraction; this facility keeps its evidenced dialect
local instead.
"""
from __future__ import annotations

import re
import shlex
import time

from hpc_agent_core import config
from hpc_agent_core.compute.base import SchedulerBackend
from hpc_agent_core.middleware import norm_path, run_command, write_remote_file
from hpc_agent_core.models import Job, JobSpec, JobState, JobStatus

_DEFAULT_RESOURCE_TYPE = "node_f"
_DEFAULT_PRIORITY = "-5"
_CUSTOM_KEYS = frozenset({
    "resource_type", "priority", "array", "hold_jid", "gpu_compute_mode",
})
_GPU_MODE_TYPES = frozenset({"node_f", "node_h", "node_q", "gpu_1"})
_ENV_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ARRAY_RE = re.compile(r"\d+(?:-\d+(?::\d+)?)?")

_GE_STATE_MAP = {
    "qw": JobState.QUEUED, "Rq": JobState.QUEUED,
    "hqw": JobState.HELD, "hRwq": JobState.HELD, "h": JobState.HELD,
    "s": JobState.HELD, "S": JobState.HELD, "T": JobState.HELD,
    "r": JobState.ACTIVE, "t": JobState.ACTIVE, "Rr": JobState.ACTIVE,
    "d": JobState.CANCELED, "dr": JobState.CANCELED,
    "E": JobState.FAILED, "Eqw": JobState.FAILED,
}


def _map_ge_state(native: str) -> JobState:
    native = native.strip()
    if native in _GE_STATE_MAP:
        return _GE_STATE_MAP[native]
    if "E" in native:
        return JobState.FAILED
    if "d" in native:
        return JobState.CANCELED
    if "r" in native or "t" in native:
        return JobState.ACTIVE
    if any(letter in native for letter in "hsST"):
        return JobState.HELD
    if "q" in native:
        return JobState.QUEUED
    return JobState.UNKNOWN


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


def _duration_hms(value: int | str) -> str:
    """Render generic day-form durations as Grid Engine's total-hour h_rt."""
    seconds = _duration_seconds(value)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _final_state(failed: str | None, exit_status: str | None) -> JobState:
    """Only call an accounting record complete when both result fields exist."""
    if failed is None or exit_status is None:
        return JobState.UNKNOWN
    try:
        failed_n = int(failed.split()[0])
        exit_n = int(exit_status.split()[0])
    except (ValueError, IndexError):
        return JobState.UNKNOWN
    return JobState.COMPLETED if failed_n == exit_n == 0 else JobState.FAILED


class TsubameBackend(SchedulerBackend):
    def __init__(self, facility: str, jobs_dir: str = "agent/jobs"):
        super().__init__(facility=facility, name="tsubame-ge")
        self._jobs_dir = jobs_dir

    @staticmethod
    def _resource_types() -> dict[str, dict]:
        return {row["name"]: row for row in config.load_facts("tsubame")["resource_types"]}

    @staticmethod
    def _resource_type(spec: JobSpec) -> str:
        return spec.attributes.custom_attributes.get(
            "resource_type", _DEFAULT_RESOURCE_TYPE)

    @staticmethod
    def _image_arg(image: str) -> str:
        if image == "~":
            return '"$HOME"'
        if image.startswith("~/"):
            return '"$HOME"/' + shlex.quote(image[2:])
        if image.startswith("$HOME/"):
            return '"$HOME"/' + shlex.quote(image[6:])
        return shlex.quote(image)

    def validate_spec(self, spec: JobSpec) -> None:
        attrs, res = spec.attributes, spec.resources
        unknown = sorted(set(attrs.custom_attributes) - _CUSTOM_KEYS)
        if unknown:
            raise ValueError(
                f"Unsupported TSUBAME custom attributes: {unknown}. Use only "
                f"{sorted(_CUSTOM_KEYS)}; arbitrary Grid Engine flags are not safe."
            )
        types = self._resource_types()
        resource_type = self._resource_type(spec)
        if resource_type not in types:
            raise ValueError(
                f"Unknown TSUBAME resource_type {resource_type!r}. Use one of "
                f"{sorted(types)} in attributes.custom_attributes."
            )
        priority = attrs.custom_attributes.get("priority", _DEFAULT_PRIORITY)
        if priority not in {"-5", "-4", "-3"}:
            raise ValueError("TSUBAME priority must be '-5', '-4', or '-3'.")
        seconds = _duration_seconds(attrs.duration)
        if seconds > 24 * 3600:
            raise ValueError("TSUBAME jobs are limited to 24 hours. Reduce attributes.duration.")
        if attrs.account in (None, ""):
            if attrs.queue_name == "prior":
                raise ValueError(
                    "TSUBAME's 'prior' subscription queue requires a project "
                    "group. Set attributes.account to one of get_projects()'s "
                    "groups (or configure defaults.group); leave queue_name "
                    "blank for the free trial."
                )
            if res.node_count > 2 or seconds > 180 or priority != "-5":
                raise ValueError(
                    "A TSUBAME trial job (no account/group) is limited to 2 "
                    "resource units, 3 minutes, and priority -5. Set "
                    "attributes.account to one of get_projects()'s groups for "
                    "a normal job, or reduce the request to those trial limits."
                )
        if attrs.queue_name not in ("", "prior"):
            raise ValueError(
                "Only the TSUBAME subscription queue 'prior' is evidenced as "
                "an explicit queue. Leave queue_name blank for normal jobs."
            )
        if res.gpus or res.gpu_cores_per_process:
            raise ValueError(
                "TSUBAME's resource_type fixes the GPU allocation, including "
                "fractional MIG slices. Leave gpus/gpu_cores_per_process unset "
                "and choose resource_type instead."
            )
        if res.memory is not None:
            raise ValueError(
                "TSUBAME's resource_type fixes memory. Leave resources.memory "
                "unset and choose a larger resource_type if needed."
            )
        if res.exclusive_node_use:
            raise ValueError(
                "TSUBAME resource types already determine the allocation. Leave "
                "exclusive_node_use false; no separate directive is verified."
            )
        if spec.stdin_path:
            raise ValueError(
                "TSUBAME stdin_path is not mapped. Leave it unset and redirect "
                "input explicitly in the executable."
            )
        for key in spec.environment:
            if not _ENV_RE.fullmatch(key):
                raise ValueError(f"Invalid shell environment variable name {key!r}.")
        array = attrs.custom_attributes.get("array")
        if array and not _ARRAY_RE.fullmatch(array):
            raise ValueError("TSUBAME array must be N or N-M[:step], for example '1-10:2'.")
        mode = attrs.custom_attributes.get("gpu_compute_mode")
        if mode is not None:
            if mode not in {"0", "1", "2"} or resource_type not in _GPU_MODE_TYPES:
                raise ValueError(
                    "gpu_compute_mode must be 0, 1, or 2 and is only valid for "
                    f"{sorted(_GPU_MODE_TYPES)}."
                )
        ranks = res.processes_per_node
        if res.process_count is not None:
            if res.process_count % res.node_count:
                raise ValueError(
                    "TSUBAME process_count must divide evenly across resource "
                    "units; set a divisible total or use processes_per_node."
                )
            ranks = res.process_count // res.node_count
        cores = ranks * (res.cpu_cores_per_process or 1)
        if cores > types[resource_type]["cores"]:
            raise ValueError(
                f"Each {resource_type} unit has {types[resource_type]['cores']} "
                f"CPU cores, but this process/thread shape needs {cores}. Reduce "
                "process_count/processes_per_node or cpu_cores_per_process."
            )

    def _header(self, spec: JobSpec) -> list[str]:
        self.validate_spec(spec)
        attrs, custom = spec.attributes, spec.attributes.custom_attributes
        resource_type = self._resource_type(spec)
        lines = ["#!/bin/sh"]
        lines.append(f"#$ -wd {shlex.quote(norm_path(spec.directory))}" if spec.directory else "#$ -cwd")
        lines.extend([
            f"#$ -l {resource_type}={spec.resources.node_count}",
            f"#$ -l h_rt={_duration_hms(attrs.duration)}",
            f"#$ -N {spec.name}",
            f"#$ -p {custom.get('priority', _DEFAULT_PRIORITY)}",
        ])
        if attrs.queue_name:
            lines.append(f"#$ -q {shlex.quote(attrs.queue_name)}")
        if custom.get("array"):
            lines.append(f"#$ -t {custom['array']}")
        if custom.get("hold_jid"):
            lines.append(f"#$ -hold_jid {shlex.quote(custom['hold_jid'])}")
        if attrs.reservation_id:
            lines.append(f"#$ -ar {shlex.quote(attrs.reservation_id)}")
        if spec.stdout_path:
            lines.append(f"#$ -o {shlex.quote(norm_path(spec.stdout_path))}")
        if spec.stderr_path:
            lines.append(f"#$ -e {shlex.quote(norm_path(spec.stderr_path))}")
        if spec.inherit_environment:
            lines.append("#$ -V")
        if custom.get("gpu_compute_mode") is not None:
            lines.append(f"#$ -v GPU_COMPUTE_MODE={custom['gpu_compute_mode']}")
        return lines

    def _body(self, spec: JobSpec) -> str:
        lines = [""]
        for key, value in spec.environment.items():
            lines.append(f"export {key}={shlex.quote(value)}")
        if spec.resources.cpu_cores_per_process and "OMP_NUM_THREADS" not in spec.environment:
            lines.append(f"export OMP_NUM_THREADS={spec.resources.cpu_cores_per_process}")
        if spec.pre_launch:
            lines.append(spec.pre_launch)
        command = spec.executable
        if spec.arguments:
            command += " " + " ".join(shlex.quote(arg) for arg in spec.arguments)
        if spec.container:
            flags = ["-B", "/gs", "-B", "/apps", "-B", "/home"]
            if self._resource_types()[self._resource_type(spec)]["gpus"]:
                flags.append("--nv")
            for mount in spec.container.volume_mounts:
                bind = f"{mount.source}:{mount.target}" + (":ro" if mount.read_only else "")
                flags.extend(["-B", shlex.quote(bind)])
            flags.append(self._image_arg(spec.container.image))
            command = "apptainer exec " + " ".join(flags) + " bash -c " + shlex.quote(command)
        if spec.launcher:
            command = spec.launcher + " " + command
        lines.append(command)
        if spec.post_launch:
            lines.append(spec.post_launch)
        lines.append("")
        return "\n".join(lines)

    def render_script(self, spec: JobSpec) -> str:
        return "\n".join(self._header(spec)) + self._body(spec)

    _SUBMIT_RE = re.compile(r"Your job(?:-array)?\s+(\d+)")

    def submit(self, spec: JobSpec) -> dict:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = write_remote_file(
            self.facility,
            f"{self._jobs_dir}/{spec.name}-{stamp}.sh",
            self.render_script(spec),
        )
        group = spec.attributes.account or None
        group_arg = f"-g {shlex.quote(group)} " if group else ""
        output = run_command(self.facility, f"qsub {group_arg}{shlex.quote(path)}")
        match = self._SUBMIT_RE.search(output)
        if not match:
            raise RuntimeError(f"qsub did not return a TSUBAME job ID: {output!r}")
        return {"job_id": match.group(1), "script_path": path, "group": group}

    @staticmethod
    def _parse_qstat_line(line: str) -> Job | None:
        tokens = line.split()
        if len(tokens) < 8 or not tokens[0].isdigit():
            return None
        jid, priority, name, user, native = tokens[:5]
        queue = ""
        slots = ""
        for token in tokens[7:]:
            if token.isdigit():
                slots = token
                break
            if not queue:
                queue = token
        return Job(id=jid, status=JobStatus(
            state=_map_ge_state(native),
            meta_data={"scheduler": "gridengine", "native_state": native,
                       "name": name, "user": user, "priority": priority,
                       "start_time": f"{tokens[5]} {tokens[6]}",
                       "queue": queue, "slots": slots},
        ))

    def _qstat_jobs(self) -> dict[str, Job]:
        jobs = {}
        for line in run_command(self.facility, "qstat").splitlines():
            if job := self._parse_qstat_line(line):
                jobs[job.id] = job
        return jobs

    @staticmethod
    def _parse_qacct_epoch(value: str) -> float | None:
        if not value or value in {"-/-", "undefined"}:
            return None
        for fmt in ("%a %b %d %H:%M:%S %Y", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
            try:
                return time.mktime(time.strptime(value.strip(), fmt))
            except ValueError:
                pass
        return None

    def _qacct_job(self, job_id: str) -> Job | None:
        try:
            output = run_command(self.facility, f"qacct -j {shlex.quote(job_id)}")
        except RuntimeError:
            return None
        if not output.strip() or "error:" in output.lower():
            return None
        fields = {}
        for line in output.splitlines():
            if line.startswith("=="):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                fields.setdefault(parts[0], parts[1].strip())
        if not fields:
            return None
        exit_code = None
        try:
            exit_code = int(fields.get("exit_status", "").split()[0])
        except (ValueError, IndexError):
            pass
        state = _final_state(fields.get("failed"), fields.get("exit_status"))
        return Job(id=job_id, status=JobStatus(
            state=state,
            time=(self._parse_qacct_epoch(fields.get("end_time", ""))
                  or self._parse_qacct_epoch(fields.get("start_time", ""))),
            exit_code=exit_code,
            message=(
                "qacct did not expose both failed and exit_status"
                if state == JobState.UNKNOWN
                else fields.get("failed") if fields.get("failed") != "0" else None
            ),
            meta_data={"scheduler": "gridengine", "native_state": "finished",
                       "name": fields.get("jobname"), "queue": fields.get("qname"),
                       "slots": fields.get("slots"), "start_time": fields.get("start_time"),
                       "end_time": fields.get("end_time"), "failed": fields.get("failed")},
        ))

    def get_statuses(self, job_ids: list[str]) -> list[Job]:
        live = self._qstat_jobs()
        result = []
        for job_id in job_ids:
            base = job_id.split(".", 1)[0]
            result.append(live.get(base) or self._qacct_job(base) or Job(
                id=job_id, status=JobStatus(
                    state=JobState.UNKNOWN,
                    message="Job is absent from qstat and qacct.",
                    meta_data={"scheduler": "gridengine"},
                )))
        return result

    def get_recent_statuses(self, since: str = "now-2days") -> list[Job]:
        return list(self._qstat_jobs().values())

    def cancel(self, job_id: str) -> Job | str:
        run_command(self.facility, f"qdel {shlex.quote(job_id)}")
        return Job(id=job_id, status=JobStatus(
            state=JobState.CANCELED, message=f"qdel {job_id} succeeded",
            meta_data={"scheduler": "gridengine"},
        ))

    def update(self, job_id: str, spec: JobSpec) -> Job:
        """Apply the four qalter changes evidenced by Tsubame4-Agent."""
        args: list[str] = []
        unsupported: list[str] = []
        top_level = spec.model_fields_set
        if "name" in top_level:
            args.extend(["-N", shlex.quote(spec.name)])
        unsupported.extend(sorted(
            top_level - {"name", "attributes", "resources", "executable"}
        ))

        attr_set = spec.attributes.model_fields_set
        if "duration" in attr_set:
            if _duration_seconds(spec.attributes.duration) > 24 * 3600:
                raise ValueError(
                    "TSUBAME jobs are limited to 24 hours. Reduce attributes.duration."
                )
            args.extend(["-l", f"h_rt={shlex.quote(_duration_hms(spec.attributes.duration))}"])
        custom = spec.attributes.custom_attributes
        if "custom_attributes" in attr_set:
            if "priority" in custom:
                if custom["priority"] not in {"-5", "-4", "-3"}:
                    raise ValueError("TSUBAME priority must be '-5', '-4', or '-3'.")
                args.extend(["-p", custom["priority"]])
            if "hold_jid" in custom:
                args.extend(["-hold_jid", shlex.quote(custom["hold_jid"])])
            unsupported.extend(
                f"attributes.custom_attributes.{key}"
                for key in sorted(set(custom) - {"priority", "hold_jid"})
            )
        unsupported.extend(
            f"attributes.{field}"
            for field in sorted(attr_set - {"duration", "custom_attributes"})
        )
        unsupported.extend(
            f"resources.{field}" for field in sorted(spec.resources.model_fields_set)
        )
        if not args:
            raise ValueError(
                "Nothing updatable in this spec. TSUBAME qalter can change "
                "name, duration, custom priority, or custom hold_jid on a "
                "queued job; set at least one of those."
                + (f" Not applied: {', '.join(unsupported)}." if unsupported else "")
            )
        run_command(
            self.facility,
            f"qalter {' '.join(args)} {shlex.quote(job_id)}",
        )
        jobs = self.get_statuses([job_id])
        job = jobs[0] if jobs else Job(
            id=job_id, status=JobStatus(state=JobState.UNKNOWN)
        )
        if unsupported and job.status:
            note = "Not applied after submission: " + ", ".join(unsupported)
            job.status.message = (
                f"{job.status.message} — {note}" if job.status.message else note
            )
        return job

    def get_live_resources(self) -> list[dict]:
        rows = []
        output = run_command(self.facility, "qstat -g c")
        for line in output.splitlines():
            parts = line.split()
            if (len(parts) >= 6 and parts[0] != "CLUSTER"
                    and not parts[0].startswith("-") and parts[2].isdigit()):
                rows.append({
                    "partition": parts[0], "load": parts[1],
                    "used": int(parts[2]), "reserved": int(parts[3]),
                    "available": int(parts[4]), "total": int(parts[5]),
                })
        return rows

    def get_projects(self) -> list[dict]:
        groups = run_command(self.facility, "id -Gn").split()
        return [{"account": group} for group in groups
                if group.startswith("tg") and group not in {"tsubame-users", "tgz-edu"}]

    def _group_points(self, group: str) -> dict | None:
        output = run_command(
            self.facility,
            f"t4-user-info group point -g {shlex.quote(group)}",
        )
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0].isdigit():
                return {"gid": parts[0], "group": parts[1],
                        "deposit": parts[2], "balance": parts[3]}
        return None

    def get_project_allocations(self, project_id: str) -> dict:
        points = self._group_points(project_id)
        if not points:
            raise ValueError(
                f"No TSUBAME point information for group {project_id!r}. Use "
                "get_projects to confirm the current user's group name."
            )
        return {"project_id": project_id, "unit": "TSUBAME points",
                "deposit": points["deposit"], "balance": points["balance"]}

    def get_user_allocations(self, project_id: str) -> dict:
        raise self._unsupported(
            "get_user_allocations",
            "TSUBAME exposes the group point balance but no separately verified per-user share",
        )

    def check_scheduler(self) -> bool:
        from hpc_agent_core.doctor import check_commands_on_path
        return check_commands_on_path(
            self.facility,
            ["qsub", "qstat", "qacct", "qdel", "qalter", "t4-user-info"],
            "tsubame-ge",
        )
