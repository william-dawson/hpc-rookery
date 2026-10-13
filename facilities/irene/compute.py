"""TGCC Irene's Bridge scheduler dialect.

Bridge resembles Slurm internally but its public interface is distinct:
``#MSUB`` directives and ``ccc_msub``/``ccc_mprun``/``ccc_mpp`` commands.
It therefore remains a facility-local SchedulerBackend.
"""
from __future__ import annotations

import re
import shlex
import time
from datetime import datetime

from hpc_agent_core.compute.base import SchedulerBackend, parse_exit_code
from hpc_agent_core.middleware import norm_path, run_command, write_remote_file
from hpc_agent_core.models import Job, JobSpec, JobState, JobStatus

_PARTITIONS = frozenset({"rome", "xlarge", "v100", "v100l", "v100l-os", "v100xl"})
_GPU_PARTITIONS = {
    "xlarge": {"cores": 112, "gpus": 1},
    "v100": {"cores": 40, "gpus": 4},
    "v100l": {"cores": 36, "gpus": 1},
    "v100l-os": {"cores": 36, "gpus": 1},
    "v100xl": {"cores": 72, "gpus": 1},
}
_CORES_PER_NODE = {
    "rome": 128, "xlarge": 112, "v100": 40,
    "v100l": 36, "v100l-os": 36, "v100xl": 72,
}
_CUSTOM_KEYS = frozenset({"filesystems", "m", "qos", "Q"})
_FILESYSTEM_RE = re.compile(r"[A-Za-z0-9._-]+(?:,[A-Za-z0-9._-]+)*")
_QOS_RE = re.compile(r"[A-Za-z0-9._-]+")
_ACCOUNT_RE = re.compile(r"[A-Za-z0-9._-]+")
_ENV_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_BRIDGE_STATE_MAP = {
    "PEN": JobState.QUEUED, "PD": JobState.QUEUED,
    "PENDING": JobState.QUEUED, "CF": JobState.QUEUED,
    "CONFIGURING": JobState.QUEUED,
    "RUN": JobState.ACTIVE, "R": JobState.ACTIVE, "R00": JobState.ACTIVE,
    "R01": JobState.ACTIVE, "RUNNING": JobState.ACTIVE,
    "COMP": JobState.ACTIVE, "COMPLETING": JobState.ACTIVE,
    "S": JobState.HELD, "SUSPENDED": JobState.HELD,
    "COMPLETED": JobState.COMPLETED, "CD": JobState.COMPLETED,
    "CANCELLED": JobState.CANCELED, "CANCELED": JobState.CANCELED,
    "CA": JobState.CANCELED,
    "FAILED": JobState.FAILED, "F": JobState.FAILED,
    "TIMEOUT": JobState.FAILED, "TO": JobState.FAILED,
    "OUT_OF_MEMORY": JobState.FAILED, "OOM": JobState.FAILED,
    "NODE_FAIL": JobState.FAILED,
}


def map_bridge_state(native: str) -> JobState:
    token = native.split()[0].rstrip("+").upper() if native.split() else ""
    return _BRIDGE_STATE_MAP.get(token, JobState.UNKNOWN)


def duration_to_seconds(duration: int | str) -> int:
    if isinstance(duration, int):
        return duration
    days = 0
    clock = duration.strip()
    if "-" in clock:
        day_text, clock = clock.split("-", 1)
        days = int(day_text)
    hours, minutes, seconds = (int(part) for part in clock.split(":"))
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _to_epoch(value: str) -> float | None:
    if not value or value in {"Unknown", "N/A", "None", "-"}:
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).timestamp()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _tasks(spec: JobSpec) -> int:
    resources = spec.resources
    return resources.process_count or resources.node_count * resources.processes_per_node


def _parse_ccc_msub_job_id(output: str) -> str:
    for line in reversed(output.strip().splitlines()):
        matches = re.findall(r"\b\d{3,}\b", line)
        if matches:
            return matches[-1]
    return ""


def _parse_compuse_projects(output: str) -> list[dict]:
    projects = []
    seen = set()
    for line in output.splitlines():
        parts = line.split()
        if not parts or "@" not in parts[0] or parts[0].lower().startswith("account"):
            continue
        project, partition = parts[0].split("@", 1)
        if (project, partition) in seen:
            continue
        seen.add((project, partition))
        projects.append({
            "account": project,
            "partition": partition,
            "status": " ".join(parts[1:]) if len(parts) > 1 else None,
        })
    return projects


def _job_from_mpp_line(line: str) -> Job | None:
    parts = line.split()
    if len(parts) < 8 or not parts[2].isdigit():
        return None
    reason = " ".join(parts[12:]) if len(parts) > 12 else None
    return Job(id=parts[2], status=JobStatus(
        state=map_bridge_state(parts[6]),
        message=reason,
        meta_data={
            "scheduler": "bridge", "user": parts[0], "account": parts[1],
            "ncpus": parts[3], "partition": parts[4], "native_state": parts[6],
            "time_limit": parts[7],
            "run_or_start": parts[8] if len(parts) > 8 else None,
            "name": parts[11] if len(parts) > 11 else None,
            "nodes_or_reason": reason,
        },
    ))


def _parse_ccc_mpp(output: str) -> list[Job]:
    return [job for line in output.splitlines()
            if (job := _job_from_mpp_line(line)) is not None]


def _parse_macct(job_id: str, output: str) -> Job:
    fields = {}
    for line in output.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip().lower()] = value.strip()
    native = "UNKNOWN"
    exit_code = None
    for line in output.splitlines():
        if " COMPLETED" in line:
            native, exit_code = "COMPLETED", 0
        elif any(marker in line for marker in (" FAILED", " TIMEOUT", " CANCELLED", " CANCELED")):
            native = line.split()[-1]
            exit_code = parse_exit_code(fields.get("exitcode", ""))
    if native == "UNKNOWN" and "execution" in fields:
        native = fields["execution"]
    return Job(id=job_id, status=JobStatus(
        state=map_bridge_state(native), time=_to_epoch(fields.get("date", "")),
        exit_code=exit_code, message=fields.get("limits"),
        meta_data={"scheduler": "bridge", "native_state": native,
                   "account": fields.get("account"), "name": fields.get("jobname"),
                   "raw": output},
    ))


class BridgeBackend(SchedulerBackend):
    def __init__(self, facility: str, jobs_dir: str = "agent/jobs"):
        super().__init__(facility=facility, name="bridge-irene")
        self._jobs_dir = jobs_dir

    def _optional(self, command: str) -> str:
        try:
            return run_command(self.facility, command)
        except RuntimeError:
            return ""

    @staticmethod
    def _filesystems(spec: JobSpec) -> str:
        custom = spec.attributes.custom_attributes
        return custom.get("filesystems") or custom.get("m") or ""

    @staticmethod
    def _cores_per_task(spec: JobSpec) -> int | None:
        resources = spec.resources
        if resources.cpu_cores_per_process:
            return resources.cpu_cores_per_process
        gpus = resources.gpus
        if not gpus:
            return None
        tasks = _tasks(spec)
        if gpus % tasks:
            raise ValueError(
                "Irene allocates GPUs indirectly from cores per task. The "
                "job-total resources.gpus must divide evenly across tasks, "
                "or set cpu_cores_per_process explicitly from live CpN/GpN."
            )
        shape = _GPU_PARTITIONS[spec.attributes.queue_name]
        return (shape["cores"] // shape["gpus"]) * (gpus // tasks)

    def validate_spec(self, spec: JobSpec) -> None:
        attrs, resources = spec.attributes, spec.resources
        if attrs.queue_name not in _PARTITIONS:
            raise ValueError(
                f"Unknown Irene partition {attrs.queue_name!r}. Set queue_name "
                f"to one of {sorted(_PARTITIONS)}; normal CPU jobs use 'rome'."
            )
        if not attrs.account:
            raise ValueError(
                "Irene requires attributes.account for #MSUB -A. Configure "
                "defaults.account or use get_projects and select one explicitly."
            )
        if not isinstance(attrs.account, str) or not _ACCOUNT_RE.fullmatch(attrs.account):
            raise ValueError(
                "Irene account must be a simple TGCC project identifier using "
                "letters, digits, dot, underscore, or hyphen. Use get_projects "
                "and copy its account field exactly."
            )
        unknown = sorted(set(attrs.custom_attributes) - _CUSTOM_KEYS)
        if unknown:
            raise ValueError(
                f"Unsupported Irene custom attributes: {unknown}. Use "
                "filesystems (or m) and qos (or Q); arbitrary #MSUB flags "
                "are not emitted by this port."
            )
        filesystems = self._filesystems(spec)
        if ("filesystems" in attrs.custom_attributes
                and "m" in attrs.custom_attributes
                and attrs.custom_attributes["filesystems"] != attrs.custom_attributes["m"]):
            raise ValueError(
                "Irene received conflicting filesystems and m values. Set only "
                "custom_attributes.filesystems."
            )
        if (not isinstance(filesystems, str) or not filesystems
                or not _FILESYSTEM_RE.fullmatch(filesystems)):
            raise ValueError(
                "Irene requires a comma-separated filesystem declaration for "
                "#MSUB -m, such as 'scratch,work'. Set custom_attributes.filesystems "
                "or configure defaults.filesystems."
            )
        qos = attrs.custom_attributes.get("qos") or attrs.custom_attributes.get("Q")
        if ("qos" in attrs.custom_attributes and "Q" in attrs.custom_attributes
                and attrs.custom_attributes["qos"] != attrs.custom_attributes["Q"]):
            raise ValueError(
                "Irene received conflicting qos and Q values. Set only "
                "custom_attributes.qos."
            )
        if qos and (not isinstance(qos, str) or not _QOS_RE.fullmatch(qos)):
            raise ValueError("Irene qos must be a simple Bridge QoS name such as 'test'.")
        if resources.gpu_cores_per_process:
            raise ValueError(
                "Irene cannot map generic gpu_cores_per_process to Bridge. Use "
                "job-total resources.gpus or set cpu_cores_per_process from "
                "the selected partition's live CpN/GpN ratio."
            )
        if resources.gpus:
            if attrs.queue_name not in _GPU_PARTITIONS:
                raise ValueError(
                    "The Irene 'rome' partition is CPU-only. Choose xlarge or "
                    "a v100-family partition for resources.gpus."
                )
            capacity = resources.node_count * _GPU_PARTITIONS[attrs.queue_name]["gpus"]
            if resources.gpus > capacity:
                raise ValueError(
                    f"Partition {attrs.queue_name!r} exposes at most {capacity} "
                    "GPU(s) across the requested nodes. Reduce resources.gpus "
                    "or increase node_count."
                )
            tasks = _tasks(spec)
            if resources.gpus % tasks:
                raise ValueError(
                    "Irene's job-total resources.gpus must divide evenly "
                    "across process_count/tasks. Adjust the task count, or "
                    "describe the verified Bridge core shape directly with "
                    "cpu_cores_per_process and leave resources.gpus unset."
                )
            if resources.cpu_cores_per_process:
                shape = _GPU_PARTITIONS[attrs.queue_name]
                required = ((shape["cores"] // shape["gpus"])
                            * (resources.gpus // tasks))
                if resources.cpu_cores_per_process < required:
                    raise ValueError(
                        f"This {attrs.queue_name} request needs at least "
                        f"{required} cores per task to allocate the requested "
                        "GPUs under the recorded CpN/GpN ratio. Increase "
                        "cpu_cores_per_process or refresh the live ratio."
                    )
        if attrs.queue_name == "xlarge" and resources.node_count != 1:
            raise ValueError("Irene xlarge jobs are recorded as single-node; set node_count=1.")
        tasks = _tasks(spec)
        cores_per_task = self._cores_per_task(spec) or 1
        if tasks * cores_per_task > resources.node_count * _CORES_PER_NODE[attrs.queue_name]:
            raise ValueError(
                f"The Irene {attrs.queue_name!r} request needs "
                f"{tasks * cores_per_task} cores across {resources.node_count} "
                "node(s), exceeding the recorded partition shape. Reduce "
                "process_count/processes_per_node or cpu_cores_per_process."
            )
        if resources.memory is not None:
            raise ValueError(
                "Irene's verified Bridge renderer has no generic memory flag. "
                "Leave resources.memory unset and choose the appropriate "
                "partition/core shape instead."
            )
        if spec.stdin_path:
            raise ValueError(
                "Irene stdin_path is not mapped. Leave it unset and redirect "
                "input explicitly in the executable."
            )
        for key in spec.environment:
            if not _ENV_RE.fullmatch(key):
                raise ValueError(f"Invalid shell environment variable name {key!r}.")

    def _header(self, spec: JobSpec) -> list[str]:
        self.validate_spec(spec)
        attrs, resources = spec.attributes, spec.resources
        lines = [
            "#!/bin/bash",
            f"#MSUB -r {spec.name}",
            f"#MSUB -q {attrs.queue_name}",
            f"#MSUB -n {_tasks(spec)}",
            f"#MSUB -T {duration_to_seconds(attrs.duration)}",
            f"#MSUB -m {self._filesystems(spec)}",
        ]
        if cores := self._cores_per_task(spec):
            lines.append(f"#MSUB -c {cores}")
        lines.append(f"#MSUB -N {resources.node_count}")
        if resources.exclusive_node_use:
            lines.append("#MSUB -x")
        lines.append(f"#MSUB -A {attrs.account}")
        lines.append(f"#MSUB -o {shlex.quote(norm_path(spec.stdout_path))}" if spec.stdout_path
                     else "#MSUB -o irene_%I.o")
        lines.append(f"#MSUB -e {shlex.quote(norm_path(spec.stderr_path))}" if spec.stderr_path
                     else "#MSUB -e irene_%I.e")
        if attrs.reservation_id:
            lines.append(f"#MSUB -E --reservation={shlex.quote(attrs.reservation_id)}")
        if qos := attrs.custom_attributes.get("qos") or attrs.custom_attributes.get("Q"):
            lines.append(f"#MSUB -Q {qos}")
        return lines

    def _body(self, spec: JobSpec) -> str:
        lines = [""]
        lines.append(f"cd {shlex.quote(norm_path(spec.directory))}" if spec.directory
                     else "cd ${BRIDGE_MSUB_PWD}")
        for key, value in spec.environment.items():
            lines.append(f"export {key}={shlex.quote(value)}")
        if spec.pre_launch:
            lines.append(spec.pre_launch)
        command = spec.executable
        if spec.arguments:
            command += " " + " ".join(shlex.quote(arg) for arg in spec.arguments)
        if spec.container:
            container = spec.container
            parts = ["ccc_mprun", "-C", shlex.quote(container.image)]
            mounts = []
            for mount in container.volume_mounts:
                text = f"src={mount.source},dst={mount.target}"
                mounts.append(text + (",ro" if mount.read_only else ""))
            if mounts:
                parts.extend(["-E", shlex.quote("--ctr-mount " + ":".join(mounts))])
            command = " ".join(parts) + " -- " + command
        else:
            launcher = spec.launcher
            if launcher is None and (_tasks(spec) > 1 or self._cores_per_task(spec)):
                launcher = "ccc_mprun"
            if launcher:
                command = launcher + " " + command
        lines.append(command)
        if spec.post_launch:
            lines.append(spec.post_launch)
        lines.append("")
        return "\n".join(lines)

    def render_script(self, spec: JobSpec) -> str:
        return "\n".join(self._header(spec)) + self._body(spec)

    def _available_projects(self) -> list[dict]:
        # Project discovery is an account API operation, not a best-effort
        # status lookup.  Propagate an SSH or Bridge failure so callers never
        # mistake an empty parsed response for a successful query with no
        # schedulable projects.
        return _parse_compuse_projects(run_command(self.facility, "ccc_compuse"))

    def _validate_live_account(self, spec: JobSpec) -> None:
        projects = self._available_projects()
        matching = [row for row in projects
                    if row["account"] == spec.attributes.account]
        if not matching:
            available = sorted({row["account"] for row in projects})
            raise ValueError(
                f"TGCC project {spec.attributes.account!r} was not available "
                f"in ccc_compuse. Use get_projects and select one of {available or ['(none parsed)']}."
            )
        if not any(row["partition"] == spec.attributes.queue_name for row in matching):
            partitions = sorted(row["partition"] for row in matching)
            raise ValueError(
                f"TGCC project {spec.attributes.account!r} is not available on "
                f"partition {spec.attributes.queue_name!r}; ccc_compuse lists {partitions}."
            )

    def submit(self, spec: JobSpec) -> dict:
        self._validate_live_account(spec)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = write_remote_file(
            self.facility, f"{self._jobs_dir}/{spec.name}-{stamp}.sh",
            self.render_script(spec),
        )
        output = run_command(self.facility, f"ccc_msub {shlex.quote(path)}")
        job_id = _parse_ccc_msub_job_id(output)
        if not job_id:
            raise RuntimeError(f"ccc_msub did not return an Irene job id: {output!r}")
        return {"job_id": job_id, "script_path": path,
                "submission_output": output.strip()}

    def get_statuses(self, job_ids: list[str]) -> list[Job]:
        live = {job.id: job for job in _parse_ccc_mpp(self._optional("ccc_mpp -u $USER"))}
        jobs = []
        for job_id in job_ids:
            if job_id in live:
                jobs.append(live[job_id])
                continue
            output = self._optional(f"ccc_macct {shlex.quote(job_id)}")
            jobs.append(_parse_macct(job_id, output) if output.strip() else Job(
                id=job_id, status=JobStatus(
                    state=JobState.UNKNOWN,
                    message="Job is absent from ccc_mpp and ccc_macct.",
                    meta_data={"scheduler": "bridge"},
                )))
        return jobs

    def get_recent_statuses(self, since: str = "now-2days") -> list[Job]:
        return _parse_ccc_mpp(self._optional("ccc_mpp -u $USER"))

    def cancel(self, job_id: str) -> Job | str:
        run_command(self.facility, f"ccc_mdel {shlex.quote(job_id)}")
        return Job(id=job_id, status=JobStatus(
            state=JobState.CANCELED, message=f"ccc_mdel {job_id} succeeded",
            meta_data={"scheduler": "bridge"},
        ))

    def update(self, job_id: str, spec: JobSpec) -> Job:
        unsupported = []
        top = spec.model_fields_set
        unsupported.extend(sorted(top - {"attributes", "resources", "executable"}))
        attr_set = spec.attributes.model_fields_set
        if "duration" not in attr_set:
            unsupported.extend(f"attributes.{field}" for field in sorted(attr_set))
            raise ValueError(
                "Irene Bridge update supports attributes.duration only; set "
                "that field on the update spec."
                + (f" Not applied: {', '.join(unsupported)}." if unsupported else "")
            )
        unsupported.extend(
            f"attributes.{field}" for field in sorted(attr_set - {"duration"})
        )
        unsupported.extend(
            f"resources.{field}" for field in sorted(spec.resources.model_fields_set)
        )
        run_command(
            self.facility,
            f"ccc_malter -T {duration_to_seconds(spec.attributes.duration)} {shlex.quote(job_id)}",
        )
        job = self.get_statuses([job_id])[0]
        if unsupported and job.status:
            note = "Not applied after submission: " + ", ".join(unsupported)
            job.status.message = f"{job.status.message} — {note}" if job.status.message else note
        return job

    def get_live_resources(self) -> list[dict]:
        output = run_command(self.facility, "ccc_mpinfo")
        partitions = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 14 or parts[0].lower() == "partition" or parts[0].startswith("-"):
                continue
            if not parts[2].isdigit():
                continue
            try:
                partitions.append({
                    "partition": parts[0], "available": parts[1],
                    "cores": {"total": int(parts[2]), "down": int(parts[3]),
                              "used": int(parts[4]), "free": int(parts[5])},
                    "memory_per_core_mb": int(parts[6]),
                    "nodes": {"total": int(parts[8]), "down": int(parts[9]),
                              "used": int(parts[10]), "free": int(parts[11])},
                    "cores_per_node": int(parts[12]),
                    "sockets_per_node": int(parts[13]) if parts[13].isdigit() else None,
                    "gpus_per_node": int(parts[16]) if len(parts) > 16 and parts[16].isdigit() else 0,
                    "gpu_type": " ".join(parts[17:]) if len(parts) > 17 else None,
                })
            except (ValueError, IndexError):
                continue
        return partitions

    def get_projects(self) -> list[dict]:
        rows = self._available_projects()
        grouped = {}
        for row in rows:
            entry = grouped.setdefault(row["account"], {
                "account": row["account"], "partitions": [], "status": [],
            })
            entry["partitions"].append(row["partition"])
            if row["status"]:
                entry["status"].append({"partition": row["partition"],
                                        "value": row["status"]})
        return [grouped[key] for key in sorted(grouped)]

    def check_scheduler(self) -> bool:
        from hpc_agent_core.doctor import check_commands_on_path
        return check_commands_on_path(
            self.facility,
            ["ccc_msub", "ccc_mprun", "ccc_mpp", "ccc_macct", "ccc_mdel",
             "ccc_malter", "ccc_mpinfo", "ccc_compuse"],
            "bridge",
        )
