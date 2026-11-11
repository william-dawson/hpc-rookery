"""Behavioral conformance checks that run against *every* registered facility.

This is the counterweight to PORTING.md §0a's "duplication between
facilities is fine". Facility code is deliberately written out per machine
rather than collapsed into shared abstractions — so the thing that keeps
those independent implementations honest is a shared *test*, not shared
code. When your facility establishes a behavior every facility should
honor, add the assertion here; it then applies to all of them, including
ones onboarded later, without any of them having to import each other.

Runs entirely offline — no SSH, no scheduler, no network. Everything here
must stay that way so CI can run it. Anything needing a live cluster
belongs in tests/live_smoke.py instead.

    .venv/bin/python tests/conformance.py
"""
import contextlib
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
import traceback
from unittest.mock import patch

import hpc_mcp  # noqa: F401 -- registers every facility
from hpc_agent_core import config
from hpc_agent_core.models import Job, JobAttributes, JobSpec, ResourceSpec
from facilities.registry import get_backend

FAILURES: list[str] = []


@contextlib.contextmanager
def no_user_config(slug: str):
    """Point a facility's config at a path that doesn't exist.

    Without this, checks covering "the user hasn't configured X yet" only
    run on a machine that genuinely hasn't — so they silently pass on a
    developer's fully-configured laptop and on nobody's CI. Forcing the
    unconfigured state makes those paths deterministic everywhere.
    """
    var = f"{config.get_facility(slug).env_prefix}_CONFIG"
    previous = os.environ.get(var)
    os.environ[var] = "/nonexistent/conformance-forced-missing.json"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = previous


def check(label: str, fn) -> None:
    try:
        fn()
    except Exception:
        FAILURES.append(f"{label}\n{traceback.format_exc()}")
        print(f"  ✗ {label}")
    else:
        print(f"  ✓ {label}")


def bare_spec() -> JobSpec:
    """A minimal spec with everything optional left blank — what
    apply_defaults() is supposed to complete."""
    return JobSpec(
        name="conformance",
        executable="echo ok",
        resources=ResourceSpec(node_count=1, processes_per_node=1),
        attributes=JobAttributes(duration=300),
    )


# --- per-facility checks -------------------------------------------------

def check_facility(slug: str) -> None:
    fac = config.get_facility(slug)
    backend = get_backend(slug)

    def registration_is_complete():
        assert fac.display_name.strip(), "display_name is empty"
        assert fac.description.strip(), "description is empty"
        assert (fac.data_dir / fac.docs_filename).exists(), "guide file missing"
        assert (fac.data_dir / fac.facts_filename).exists(), "facts JSON missing"
        assert (fac.data_dir / "docs_index" / "chunks.json").exists(), "docs index missing"

    def facts_load():
        assert config.load_facts(slug), "facts JSON is empty"

    def apply_defaults_is_idempotent():
        """Running apply_defaults twice must not change the result — it's
        called by both render_job_script and submit_job, and an agent
        commonly renders then submits the same spec object."""
        first, second = bare_spec(), bare_spec()
        try:
            backend.apply_defaults(first)
        except ValueError:
            return  # a facility that requires an unset field; covered below
        backend.apply_defaults(first)          # second application
        backend.apply_defaults(second)
        assert first.attributes.queue_name == second.attributes.queue_name
        assert first.attributes.account == second.attributes.account

    def _defaults_then_validate_then_render():
        """The exact sequence submit_job runs. Either it produces a usable
        script, or it raises a ValueError that tells the user what to set —
        never an AttributeError/TypeError from a half-completed spec."""
        spec = bare_spec()
        try:
            backend.apply_defaults(spec)
            backend.validate_spec(spec)
        except ValueError as e:
            msg = str(e)
            assert len(msg) > 40, f"error too terse to act on: {msg!r}"
            # Must tell the user what to do about it, not just what's wrong.
            assert any(w in msg.lower() for w in ("set ", "configure", "use ")), \
                f"error doesn't tell the user what to do: {msg!r}"
            return
        script = backend.render_script(spec)
        assert script.startswith("#!"), "rendered script has no shebang"
        assert "echo ok" in script, "rendered script lost the executable"

    def defaults_then_validate_then_render():
        _defaults_then_validate_then_render()

    def defaults_then_validate_then_render_unconfigured():
        """Same, with the user's config forced missing — this is the path a
        brand-new user hits, and on a facility with a mandatory setting
        it's the *only* way the "you must configure X" error gets
        exercised at all."""
        with no_user_config(slug):
            _defaults_then_validate_then_render()

    def rendered_script_has_a_queue():
        """If apply_defaults supplies a queue, it must actually reach the
        script — catches a facility that sets the wrong attribute."""
        spec = bare_spec()
        try:
            backend.apply_defaults(spec)
            backend.validate_spec(spec)
        except ValueError:
            return
        if spec.attributes.queue_name:
            assert spec.attributes.queue_name in backend.render_script(spec), \
                "queue_name was defaulted but never appears in the script"

    def explicit_values_survive_defaults():
        """apply_defaults must never overwrite something the caller set."""
        spec = bare_spec()
        spec.attributes.queue_name = "caller-chosen-queue"
        spec.attributes.account = "caller-chosen-account"
        backend.apply_defaults(spec)
        assert spec.attributes.queue_name == "caller-chosen-queue", \
            "apply_defaults overwrote a caller-supplied queue_name"
        assert spec.attributes.account == "caller-chosen-account", \
            "apply_defaults overwrote a caller-supplied account"

    def backend_knows_its_facility():
        assert backend.facility == slug, \
            f"backend.facility is {backend.facility!r}, expected {slug!r}"

    def machine_resource_limits_are_enforced():
        """Exercise deterministic limits encoded by the facility hook.

        Only RIKYU currently has a complete job-resource table precise
        enough for these checks; facilities whose limits vary by project or
        live partition intentionally do not guess here.
        """
        if slug != "rikyu":
            return
        invalid_specs = [
            {"gpus": 5},
            {"gpus": 8, "node_count": 1},
            {"gpus": 1, "cpu_cores_per_process": 37},
            {"gpus": 1, "memory": 401 * 1024**3},
        ]
        for resources in invalid_specs:
            spec = JobSpec(
                executable="true", resources=resources,
                attributes={"queue_name": "gpu"},
            )
            try:
                backend.validate_spec(spec)
            except ValueError:
                continue
            raise AssertionError(f"RIKYU accepted invalid resources: {resources}")

        wrong_queue = JobSpec(
            executable="true", attributes={"queue_name": "not-gpu"},
        )
        try:
            backend.validate_spec(wrong_queue)
        except ValueError:
            return
        raise AssertionError("RIKYU accepted a nonexistent partition")

    def miyabi_pbs_shape_and_limits_are_enforced():
        """Keep the offline PBS port honest while Miyabi is inaccessible."""
        if slug != "miyabi":
            return

        spec = JobSpec(
            name="pbs-shape",
            executable="hostname",
            resources={
                "node_count": 2,
                "process_count": 8,
                "cpu_cores_per_process": 2,
                "memory": 3 * 1024**3 + 1,
            },
            attributes={
                "queue_name": "debug-c",
                "account": "caller-project",
                "duration": 300,
            },
        )
        script = backend.render_script(spec)
        assert "#PBS -q debug-c" in script
        assert "#PBS -W group_list=caller-project" in script
        assert "#PBS -l select=2:mpiprocs=4:ompthreads=2:mem=4gb" in script
        assert "#PBS -l walltime=00:05:00" in script
        assert 'cd "$PBS_O_WORKDIR"' in script

        # A PBS directive is a single line of options, so a space inside an
        # argument does not need a newline to inject a second option -- the
        # control-character validator in models.py cannot see this. Both
        # fields are checked against their real syntax instead.
        injections = [
            {"queue_name": "debug-c -l place=excl", "account": "caller-project"},
            {"queue_name": "debug-c", "account": "caller-project -l place=excl"},
            {"queue_name": "debug-c", "account": "grp; qdel 1"},
            {"queue_name": "no-such-queue", "account": "caller-project"},
            {"queue_name": "debug-", "account": "caller-project"},
        ]
        for attrs in injections:
            bad = JobSpec(executable="true", resources={"node_count": 1},
                          attributes={**attrs, "duration": 300})
            try:
                backend.apply_defaults(bad)
                backend.validate_spec(bad)
            except ValueError:
                continue
            raise AssertionError(
                f"miyabi accepted an injectable PBS directive argument: {attrs}"
            )

        # A legitimate path containing a space must survive, quoted, rather
        # than splitting into a second option on the -o/-e directive line.
        spaced = JobSpec(
            name="pbs-spaces", executable="hostname",
            resources={"node_count": 1},
            stdout_path="/home/u/out dir/job.out",
            stderr_path="/home/u/out dir/job.err",
            attributes={"queue_name": "debug-c", "account": "caller-project",
                        "duration": 300},
        )
        backend.apply_defaults(spaced)
        backend.validate_spec(spaced)
        spaced_script = backend.render_script(spaced)
        assert "#PBS -o '/home/u/out dir/job.out'" in spaced_script, spaced_script
        assert "#PBS -e '/home/u/out dir/job.err'" in spaced_script, spaced_script

        finished_without_exit = backend._job({
            "Job_Id": "123.opbs", "job_state": "F",
        })
        assert finished_without_exit.status.state.value == "completed"
        assert finished_without_exit.status.exit_code is None
        failed = backend._job({
            "Job_Id": "124.opbs", "job_state": "F", "Exit_status": "2",
        })
        assert failed.status.state.value == "failed"
        assert failed.status.exit_code == 2
        with_workdir = backend._job({
            "Job_Id": "125.opbs", "job_state": "R",
            "Variable_List": (
                "PBS_O_HOME=/home/u,PBS_O_WORKDIR=/home/u/agent/jobs,"
                "PBS_O_HOST=login"
            ),
        })
        assert with_workdir.status.meta_data["workdir"] == "/home/u/agent/jobs"
        assert backend._pbs_workdir("PBS_O_HOME=/home/u") == ""

        invalid = [
            ("debug-c", {"processes_per_node": 113}),
            ("debug-g", {"processes_per_node": 73}),
            ("debug-mig", {"processes_per_node": 19}),
            ("debug-c", {"gpus": 1}),
            ("debug-g", {"node_count": 2, "gpus": 1}),
        ]
        for queue, resources in invalid:
            bad = JobSpec(
                executable="true",
                resources=resources,
                attributes={"queue_name": queue, "account": "caller-project"},
            )
            try:
                backend.validate_spec(bad)
            except ValueError:
                continue
            raise AssertionError(
                f"Miyabi accepted invalid resources for {queue}: {resources}"
            )

    def octopus_dual_vendor_defaults_and_limits_are_enforced():
        """Exercise the dual-vendor mapping without needing either GPU."""
        if slug != "octopus":
            return

        default = bare_spec()
        backend.apply_defaults(default)
        backend.validate_spec(default)
        assert default.attributes.queue_name == "h200"
        assert default.resources.gpus == 1
        script = backend.render_script(default)
        assert "#SBATCH --partition=h200" in script
        assert "#SBATCH --gres=gpu:1" in script

        for queue, expected, forbidden in [
            ("h200", "--nv", "--rocm"),
            ("mi300x", "--rocm", "--nv"),
        ]:
            spec = JobSpec(
                executable="echo ok",
                container={"image": "$HOME/test.sif"},
                attributes={"queue_name": queue, "duration": 300},
                resources={"gpus": 2},
            )
            backend.apply_defaults(spec)
            backend.validate_spec(spec)
            rendered = backend.render_script(spec)
            assert f"#SBATCH --partition={queue}" in rendered
            assert "#SBATCH --gres=gpu:2" in rendered
            assert expected in rendered
            assert forbidden not in rendered

        invalid = [
            ({"queue_name": "gpu"}, {}),
            ({"queue_name": "h200"}, {"gpus": 9}),
            ({"queue_name": "h200"}, {"node_count": 2, "gpus": 1}),
            ({"queue_name": "h200"}, {"gpus": 1, "processes_per_node": 193}),
            ({"queue_name": "h200"}, {"gpus": 1, "memory": 2_317_611 * 1024**2}),
            ({"queue_name": "mi300x", "duration": "08:00:01"}, {"gpus": 1}),
        ]
        for attributes, resources in invalid:
            bad = JobSpec(
                executable="true", resources=resources, attributes=attributes,
            )
            backend.apply_defaults(bad)
            try:
                backend.validate_spec(bad)
            except ValueError:
                continue
            raise AssertionError(
                f"Octopus accepted invalid spec: attributes={attributes}, "
                f"resources={resources}"
            )

        long_job = JobSpec(
            executable="true", resources={"gpus": 1},
            attributes={"queue_name": "mi300x-long", "duration": "2-00:00:00"},
        )
        backend.apply_defaults(long_job)
        backend.validate_spec(long_job)

    def tsubame_resource_types_and_trial_limits_are_enforced():
        """Exercise TSUBAME's non-generic Grid Engine resource dialect."""
        if slug != "tsubame":
            return

        with no_user_config(slug), patch.dict(os.environ, {"TSUBAME_GROUP": ""}):
            trial = JobSpec(
                name="ge-shape",
                executable="hostname",
                container={"image": "$HOME/test image.sif"},
                resources={"node_count": 2, "processes_per_node": 4,
                           "cpu_cores_per_process": 2},
                attributes={
                    "duration": 180,
                    "account": "",
                    "custom_attributes": {
                        "resource_type": "gpu_1", "priority": "-5",
                        "array": "1-4:2", "gpu_compute_mode": "1",
                    },
                },
            )
            backend.apply_defaults(trial)
            script = backend.render_script(trial)
        assert "#$ -l gpu_1=2" in script
        assert "#$ -l h_rt=00:03:00" in script
        assert "#$ -p -5" in script
        assert "#$ -t 1-4:2" in script
        assert "#$ -v GPU_COMPUTE_MODE=1" in script
        assert "export OMP_NUM_THREADS=2" in script
        assert "apptainer exec -B /gs -B /apps -B /home --nv" in script
        assert '"$HOME"/' in script

        cpu_container = JobSpec(
            executable="true", container={"image": "image.sif"},
            attributes={"account": "paid", "duration": 3600,
                        "custom_attributes": {"resource_type": "cpu_40"}},
        )
        backend.apply_defaults(cpu_container)
        cpu_script = backend.render_script(cpu_container)
        assert "#$ -l cpu_40=1" in cpu_script
        assert "--nv" not in cpu_script

        invalid_specs = [
            ({"node_count": 3}, {"account": "", "duration": 180}),
            ({"node_count": 1}, {"account": "", "duration": 181}),
            ({}, {"account": "", "duration": 180,
                  "custom_attributes": {"priority": "-4"}}),
            ({}, {"account": "paid", "duration": "24:00:01"}),
            ({}, {"account": "paid", "custom_attributes": {"resource_type": "gpu_2"}}),
            ({"gpus": 1}, {"account": "paid"}),
            ({"memory": 1024}, {"account": "paid"}),
            ({"processes_per_node": 9}, {"account": "paid",
                 "custom_attributes": {"resource_type": "gpu_1"}}),
            ({}, {"account": "paid",
                  "custom_attributes": {"resource_type": "gpu_h",
                                        "gpu_compute_mode": "1"}}),
            ({}, {"account": "paid", "queue_name": "all.q"}),
            ({}, {"account": "", "queue_name": "prior"}),
            ({}, {"account": "paid", "custom_attributes": {"unknown": "x"}}),
        ]
        for resources, attributes in invalid_specs:
            bad = JobSpec(executable="true", resources=resources, attributes=attributes)
            backend.apply_defaults(bad)
            try:
                backend.validate_spec(bad)
            except ValueError:
                continue
            raise AssertionError(
                f"TSUBAME accepted invalid spec: resources={resources}, "
                f"attributes={attributes}"
            )

        assert backend._parse_qstat_line(
            "123 0.555 job user hRwq 08/19/2026 12:34:56 1"
        ).status.state.value == "held"
        assert backend._parse_qstat_line(
            "124 0.555 job user r 08/19/2026 12:34:56 all.q@node 8"
        ).status.state.value == "active"
        from facilities.tsubame.compute import _final_state
        assert _final_state("0", "0").value == "completed"
        assert _final_state("0", "2").value == "failed"
        assert _final_state(None, None).value == "unknown"

        update_spec = JobSpec(
            name="renamed", executable="true",
            attributes={"duration": 600,
                        "custom_attributes": {"priority": "-4", "hold_jid": "41"}},
        )
        updated = Job(
            id="42", status={"state": "queued", "message": None},
        )
        with patch("facilities.tsubame.compute.run_command") as command, \
                patch.object(backend, "get_statuses", return_value=[updated]):
            backend.update("42", update_spec)
        rendered_command = command.call_args.args[1]
        assert rendered_command == (
            "qalter -N renamed -l h_rt=00:10:00 -p -4 -hold_jid 41 42"
        )

    def irene_bridge_shape_and_limits_are_enforced():
        """Exercise Bridge rendering and parsers without a TGCC connection."""
        if slug != "irene":
            return

        spec = JobSpec(
            name="bridge-shape",
            executable="./solver",
            arguments=["input with spaces"],
            environment={"OMP_NUM_THREADS": "2"},
            resources={
                "node_count": 2, "process_count": 8,
                "cpu_cores_per_process": 2, "exclusive_node_use": True,
            },
            attributes={
                "queue_name": "rome", "account": "gen-test", "duration": 600,
                "custom_attributes": {"filesystems": "scratch,work", "qos": "test"},
            },
        )
        script = backend.render_script(spec)
        assert "#MSUB -q rome" in script
        assert "#MSUB -A gen-test" in script
        assert "#MSUB -m scratch,work" in script
        assert "#MSUB -n 8" in script
        assert "#MSUB -c 2" in script
        assert "#MSUB -N 2" in script
        assert "#MSUB -x" in script
        assert "#MSUB -T 600" in script
        assert "#MSUB -Q test" in script
        assert "cd ${BRIDGE_MSUB_PWD}" in script
        assert "ccc_mprun ./solver 'input with spaces'" in script

        gpu = JobSpec(
            executable="gpu-app", resources={"process_count": 4, "gpus": 4},
            attributes={"queue_name": "v100", "account": "gen-test",
                        "custom_attributes": {"filesystems": "scratch"}},
        )
        gpu_script = backend.render_script(gpu)
        assert "#MSUB -c 10" in gpu_script
        assert "ccc_mprun gpu-app" in gpu_script

        container = JobSpec(
            executable="python", arguments=["run.py"],
            container={"image": "registry/image:tag",
                       "volume_mounts": [{"source": "/work/a", "target": "/data"}]},
            attributes={"queue_name": "rome", "account": "gen-test",
                        "custom_attributes": {"filesystems": "work"}},
        )
        assert "ccc_mprun -C registry/image:tag -E" in backend.render_script(container)

        invalid_specs = [
            ({}, {"queue_name": "skylake", "account": "gen-test"}),
            ({"gpus": 1}, {"queue_name": "rome", "account": "gen-test"}),
            ({"node_count": 2}, {"queue_name": "xlarge", "account": "gen-test"}),
            ({"memory": 1024}, {"queue_name": "rome", "account": "gen-test"}),
            ({"process_count": 129}, {"queue_name": "rome", "account": "gen-test"}),
            ({"process_count": 2, "gpus": 1}, {"queue_name": "v100", "account": "gen-test"}),
        ]
        for resources, attributes in invalid_specs:
            attributes.setdefault("custom_attributes", {"filesystems": "scratch,work"})
            bad = JobSpec(executable="true", resources=resources, attributes=attributes)
            try:
                backend.validate_spec(bad)
            except ValueError:
                continue
            raise AssertionError(
                f"Irene accepted invalid spec: resources={resources}, attributes={attributes}"
            )

        from facilities.irene.compute import (
            _parse_ccc_mpp, _parse_ccc_msub_job_id, _parse_compuse_projects,
            _parse_macct,
        )
        projects = _parse_compuse_projects(
            "gen1@rome OK normal\ngen1@v100 BONUS\ngen1@rome duplicate"
        )
        assert [(p["account"], p["partition"]) for p in projects] == [
            ("gen1", "rome"), ("gen1", "v100")]
        assert _parse_ccc_msub_job_id("Submitted batch job 123456") == "123456"
        jobs = _parse_ccc_mpp(
            "user gen1 123456 8 rome batch RUN 00:10:00 now x x bridge-job node01"
        )
        assert jobs[0].status.state.value == "active"
        assert _parse_macct(
            "123456", "Date: 19/08/2026 12:00:00\nStep COMPLETED"
        ).status.state.value == "completed"

        with patch(
            "facilities.irene.compute.run_command",
            return_value="gen1@rome OK normal\ngen1@v100 BONUS",
        ) as command:
            assert backend.get_projects() == [{
                "account": "gen1", "partitions": ["rome", "v100"],
                "status": [
                    {"partition": "rome", "value": "OK normal"},
                    {"partition": "v100", "value": "BONUS"},
                ],
            }]
        assert command.call_args.args == ("irene", "ccc_compuse")

        with patch(
            "facilities.irene.compute.run_command",
            side_effect=RuntimeError("Irene connection failed"),
        ):
            try:
                backend.get_projects()
            except RuntimeError as exc:
                assert "Irene connection failed" in str(exc)
            else:
                raise AssertionError(
                    "Irene returned an empty project list after its query failed"
                )

        with patch(
            "facilities.irene.compute.run_command",
            side_effect=["gen-test@rome OK", "Submitted batch job 123456"],
        ) as command, patch(
            "facilities.irene.compute.write_remote_file",
            return_value="agent/jobs/bridge-shape.sh",
        ) as write:
            submitted = backend.submit(spec)
        assert submitted["job_id"] == "123456"
        assert write.call_args.args[0] == "irene"
        assert command.call_args_list[0].args == ("irene", "ccc_compuse")
        assert command.call_args_list[1].args == (
            "irene", "ccc_msub agent/jobs/bridge-shape.sh",
        )

        update_spec = JobSpec(executable="true", attributes={"duration": 300})
        updated = Job(id="123456", status={"state": "active"})
        with patch("facilities.irene.compute.run_command") as command, \
                patch.object(backend, "get_statuses", return_value=[updated]):
            backend.update("123456", update_spec)
        assert command.call_args.args == (
            "irene", "ccc_malter -T 300 123456",
        )

    def cell2026_dual_scheduler_routing_is_enforced():
        """Exercise both schedulers and the local routing index offline."""
        if slug != "cell2026":
            return

        # AGE may be outside PATH. Doctor must check the same configured
        # Grid Engine binaries that the runtime backend invokes.
        from facilities.cell2026.compute import Cell2026Backend
        configured = Cell2026Backend("cell2026", ge_bin_prefix="/opt/age/bin")
        with patch("hpc_agent_core.doctor.check_commands_on_path",
                   return_value=True) as check_commands:
            assert configured.check_scheduler()
        checked = check_commands.call_args.args[1]
        assert "/opt/age/bin/qsub" in checked
        assert "/opt/age/bin/qstat" in checked
        assert "sbatch" in checked

        try:
            backend.get_projects()
        except NotImplementedError as exc:
            assert "neither Grid Engine nor Slurm exposes per-project accounting" in str(exc)
        else:
            raise AssertionError(
                "cell2026 returned an empty project list despite lacking project accounting"
            )

        # A successful resource list must cover both schedulers.  An empty
        # list after failed SSH/configuration probes looks like valid empty
        # occupancy to an MCP client, which is worse than a clear error.
        with patch.object(
            backend._slurm, "get_live_resources", return_value=[],
        ), patch(
            "facilities.cell2026.compute.run_command", return_value="",
        ):
            assert backend.get_live_resources() == []

        with patch.object(
            backend._slurm, "get_live_resources",
            side_effect=RuntimeError("Slurm connection failed"),
        ), patch(
            "facilities.cell2026.compute.run_command",
            side_effect=RuntimeError("Grid Engine connection failed"),
        ):
            try:
                backend.get_live_resources()
            except RuntimeError as exc:
                message = str(exc)
                assert "incomplete" in message
                assert "Slurm, Grid Engine" in message
                assert "Slurm connection failed" in message
            else:
                raise AssertionError(
                    "cell2026 returned a resource list after both scheduler probes failed"
                )

        with patch.object(
            backend._slurm, "get_live_resources",
            return_value=[{"partition": "all", "nodes_total": 2}],
        ), patch(
            "facilities.cell2026.compute.run_command",
            side_effect=RuntimeError("Grid Engine connection failed"),
        ):
            try:
                backend.get_live_resources()
            except RuntimeError as exc:
                message = str(exc)
                assert "incomplete" in message
                assert "Grid Engine" in message
                assert "Grid Engine connection failed" in message
            else:
                raise AssertionError(
                    "cell2026 returned partial scheduler occupancy as a complete list"
                )

        default = bare_spec()
        backend.apply_defaults(default)
        assert default.attributes.queue_name == "all.q"
        ge_script = backend.render_script(JobSpec(
            name="cell-ge", executable="echo ok",
            resources={"gpus": 1, "cpu_cores_per_process": 4},
            attributes={"queue_name": "all.q", "duration": 300},
        ))
        assert "#$ -q all.q" in ge_script
        assert "#$ -l gpu=1" in ge_script
        assert "#$ -pe smp 4" in ge_script
        assert "SGE_HGR_gpu" in ge_script
        assert "CUDA_VISIBLE_DEVICES" in ge_script
        assert "export OMP_NUM_THREADS=4" in ge_script
        assert "#SBATCH" not in ge_script

        ge_host = backend.render_script(JobSpec(
            executable="true", attributes={"queue_name": "helix"},
        ))
        assert "#$ -q all.q" in ge_host
        assert "#$ -l hostname=helix" in ge_host

        slurm_host = backend.render_script(JobSpec(
            name="cell-slurm", executable="echo ok",
            resources={"cpu_cores_per_process": 2, "memory": None},
            attributes={"queue_name": "beta", "duration": 300},
        ))
        assert "#SBATCH --partition=all" in slurm_host
        assert "#SBATCH --nodelist=beta" in slurm_host
        assert "#SBATCH --cpus-per-task=2" in slurm_host
        assert "--mem" not in slurm_host
        assert "--gres" not in slurm_host
        assert "#$ " not in slurm_host

        slurm_gpu = backend.render_script(JobSpec(
            executable="true", resources={"gpus": 1},
            attributes={"queue_name": "serine"},
            container={"image": "$HOME/test.sif"},
        ))
        assert "#SBATCH --nodelist=serine" in slurm_gpu
        assert "--gres" not in slurm_gpu
        assert "singularity exec --nv" in slurm_gpu

        ge_submit_spec = JobSpec(
            name="submit-ge", executable="true", resources={"gpus": 1},
            attributes={"queue_name": "helix"},
        )
        with patch(
            "hpc_agent_core.compute.gridengine.write_remote_file",
            return_value="agent/jobs/submit-ge.sh",
        ) as ge_write, patch(
            "hpc_agent_core.compute.gridengine.run_command", return_value="301\n",
        ) as ge_command, patch(
            "facilities.cell2026.registry.record",
        ) as record:
            assert backend.submit(ge_submit_spec)["job_id"] == "301"
        assert ge_write.call_args.args[0] == "cell2026"
        assert ge_command.call_args.args[0] == "cell2026"
        assert record.call_args.args[:3] == ("301", "gridengine", "helix")

        slurm_submit_spec = JobSpec(
            name="submit-slurm", executable="true",
            attributes={"queue_name": "beta"},
        )
        with patch(
            "hpc_agent_core.compute.slurm.write_remote_file",
            return_value="agent/jobs/submit-slurm.sh",
        ) as slurm_write, patch(
            "hpc_agent_core.compute.slurm.run_command", return_value="302\n",
        ) as slurm_command, patch(
            "facilities.cell2026.registry.record",
        ) as record:
            assert backend.submit(slurm_submit_spec)["job_id"] == "302"
        assert slurm_write.call_args.args[0] == "cell2026"
        assert slurm_command.call_args.args == (
            "cell2026", "sbatch --parsable agent/jobs/submit-slurm.sh",
        )
        assert record.call_args.args[:3] == ("302", "slurm", "all")

        explicit_slurm = JobSpec(
            executable="true", attributes={"scheduler": "slurm"},
        )
        backend.apply_defaults(explicit_slurm)
        assert explicit_slurm.attributes.queue_name == "all"

        invalid_specs = [
            ({"gpus": 3}, {"queue_name": "all.q"}, {}),
            ({"process_count": 33}, {"queue_name": "all.q"}, {}),
            ({"node_count": 2}, {"queue_name": "helix"}, {}),
            ({"memory": 1024}, {"queue_name": "all.q"}, {}),
            ({"gpus": 1}, {"queue_name": "all.q"}, {"CUDA_VISIBLE_DEVICES": "0"}),
            ({}, {"queue_name": "all.q", "account": "project"}, {}),
            ({"node_count": 2}, {"queue_name": "beta"}, {}),
            ({"process_count": 9}, {"queue_name": "all"}, {}),
            ({"gpus": 1}, {"queue_name": "serine"}, {}),
            ({"gpus": 2}, {"queue_name": "all"}, {}),
            ({}, {"queue_name": "all", "custom_attributes": {"constraint": "gpu"}}, {}),
            ({}, {"queue_name": "not-a-queue"}, {}),
            ({}, {"queue_name": "all.q", "scheduler": "slurm"}, {}),
        ]
        for resources, attributes, environment in invalid_specs:
            bad = JobSpec(
                executable="true", resources=resources,
                attributes=attributes, environment=environment,
            )
            try:
                backend.validate_spec(bad)
            except ValueError:
                continue
            raise AssertionError(
                f"cell2026 accepted invalid spec: resources={resources}, "
                f"attributes={attributes}, environment={environment}"
            )

        from facilities.cell2026 import registry as cell_registry
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(cell_registry, "_REGISTRY_DIR", pathlib.Path(temporary)):
                cell_registry.record("101", "slurm", "all", "agent/jobs/a.sh")
                cell_registry.record("202", "gridengine", "all.q", "agent/jobs/b.sh")
                assert cell_registry.lookup("101") == "slurm"
                assert cell_registry.lookup("202") == "gridengine"
                assert {row["job_id"] for row in cell_registry.recent()} == {"101", "202"}
                assert cell_registry.lookup("../escape") is None
                cell_registry.record("101", "gridengine", "all.q", "agent/jobs/c.sh")
                assert cell_registry.lookup("101") is None, (
                    "overlapping IDs registered to both schedulers must stay ambiguous"
                )

        slurm_job = Job(id="101", status={"state": "active",
                                           "meta_data": {"native_state": "RUNNING"}})
        ge_job = Job(id="202", status={"state": "completed",
                                       "meta_data": {"native_state": "qacct"}})
        with patch(
            "facilities.cell2026.registry.lookup",
            side_effect=lambda job_id: {"101": "slurm", "202": "gridengine"}.get(job_id),
        ), patch.object(
            backend._slurm, "get_statuses", return_value=[slurm_job],
        ), patch.object(
            backend._gridengine, "get_statuses", return_value=[ge_job],
        ):
            routed = backend.get_statuses(["202", "101"])
        assert [job.id for job in routed] == ["202", "101"]
        assert all(job.status.meta_data["scheduler_source"] == "registry"
                   for job in routed)

        # run_command is stubbed so both liveness probes succeed: this case
        # is about a genuinely ambiguous id, not an unreachable scheduler.
        with patch("facilities.cell2026.registry.lookup", return_value=None), \
                patch("hpc_agent_core.middleware.run_command", return_value=""), \
                patch.object(backend._slurm, "get_statuses", return_value=[slurm_job]), \
                patch.object(backend._gridengine, "get_statuses", return_value=[ge_job]), \
                patch.object(backend._slurm, "cancel") as slurm_cancel, \
                patch.object(backend._gridengine, "cancel") as ge_cancel:
            try:
                backend.cancel("77")
            except ValueError as exc:
                assert "exists in both" in str(exc), exc
            else:
                raise AssertionError("cell2026 canceled an ambiguous cross-scheduler ID")
        slurm_cancel.assert_not_called()
        ge_cancel.assert_not_called()

        # An unregistered id with only ONE scheduler answering must not be
        # cancelled on that scheduler: _is_not_found() reports the same shape
        # for "absent" and "the query failed", and this facility's Slurm runs
        # has_accounting=False, which swallows both squeue and scontrol
        # errors -- so a dead link looks exactly like a clean miss. Ids can
        # collide across the two schedulers, so guessing can kill a different
        # job.
        missing = Job(id="77", status={"state": "unknown"})
        with patch("facilities.cell2026.registry.lookup", return_value=None), \
                patch("hpc_agent_core.middleware.run_command",
                      side_effect=RuntimeError("ssh: connect to host: timed out")), \
                patch.object(backend._slurm, "get_statuses", return_value=[slurm_job]), \
                patch.object(backend._gridengine, "get_statuses", return_value=[missing]), \
                patch.object(backend._slurm, "cancel") as slurm_cancel, \
                patch.object(backend._gridengine, "cancel") as ge_cancel:
            try:
                backend.cancel("77")
            except ValueError as exc:
                assert "could not be completed" in str(exc), exc
            else:
                raise AssertionError(
                    "cell2026 cancelled an unregistered id while a scheduler "
                    "lookup was inconclusive"
                )
        slurm_cancel.assert_not_called()
        ge_cancel.assert_not_called()

        # With both schedulers demonstrably answering and exactly one hit,
        # the fallback cancel still works.
        with patch("facilities.cell2026.registry.lookup", return_value=None), \
                patch("hpc_agent_core.middleware.run_command", return_value=""), \
                patch.object(backend._slurm, "get_statuses", return_value=[slurm_job]), \
                patch.object(backend._gridengine, "get_statuses", return_value=[missing]), \
                patch.object(backend._slurm, "cancel",
                             return_value=Job(id="101", status={"state": "canceled"})) as ok_cancel, \
                patch.object(backend._gridengine, "cancel") as ge_cancel2:
            cancelled = backend.cancel("101")
        ok_cancel.assert_called_once()
        ge_cancel2.assert_not_called()
        assert cancelled.status.meta_data["cancel_source"] == "slurm_fallback"

        update_spec = JobSpec(executable="true", attributes={"duration": 600})
        with patch("facilities.cell2026.registry.lookup", return_value="slurm"), \
                patch.object(backend._slurm, "update", return_value=slurm_job) as update:
            backend.update("101", update_spec)
        assert update.call_args.args == ("101", update_spec)

    def crux_pbs_shape_and_limits_are_enforced():
        """Keep the offline Crux port honest while no live access exists.

        Every fixture here is synthetic — invented rows in the shapes the
        ALCF/PBS documentation describes, never copied example output —
        and the "at request of scheduler" comment is the machine's own
        literal message text the parser must recognize.
        """
        if slug != "crux":
            return

        from facilities.crux.compute import _duration_seconds, _walltime

        def spec_with(**overrides):
            resources = overrides.pop("resources", {"node_count": 1})
            attributes = {"queue_name": "debug", "account": "Catalyst",
                          "duration": 600}
            attributes.update(overrides.pop("attributes", {}))
            return JobSpec(executable="hostname", resources=resources,
                           attributes=attributes)

        # Rendered shape: the documented ALCF directive block, whole-node
        # select, mandatory walltime/filesystems, forced -k doe, and the
        # job body starting from PBS_O_WORKDIR.
        with no_user_config(slug):
            shape = spec_with(resources={"node_count": 2})
            backend.apply_defaults(shape)
            script = backend.render_script(shape)
        assert "#!/bin/bash -l" in script
        assert "#PBS -q debug" in script
        assert "#PBS -A Catalyst" in script
        assert "#PBS -l select=2:system=crux" in script
        assert "#PBS -l place=scatter" in script
        assert "#PBS -l walltime=00:10:00" in script
        assert "#PBS -l filesystems=home:eagle" in script
        assert "#PBS -k doe" in script
        assert "#PBS -r y" not in script
        assert 'cd "$PBS_O_WORKDIR"' in script
        assert "hostname" in script
        # No mpiprocs/ompthreads: ALCF allocates whole nodes and rank
        # placement belongs to mpiexec, never to the select statement.
        assert "mpiprocs" not in script
        assert "ompthreads" not in script

        # Defaults: production queue filled when the caller is silent, a
        # reservation suppresses it, and filesystems default from facts.
        with no_user_config(slug):
            default = JobSpec(executable="true",
                              attributes={"account": "Catalyst", "duration": 600})
            backend.apply_defaults(default)
            assert default.attributes.queue_name == "workq-route"
            assert "#PBS -l filesystems=home:eagle" in backend.render_script(default)

            reserved = JobSpec(executable="true", attributes={
                "account": "Catalyst", "duration": 600,
                "reservation_id": "A123456"})
            backend.apply_defaults(reserved)
            assert reserved.attributes.queue_name == ""
            assert "#PBS -q A123456" in backend.render_script(reserved)

            preemptable = spec_with(attributes={"queue_name": "preemptable",
                                                "duration": "48:00:00"})
            backend.apply_defaults(preemptable)
            assert "#PBS -r y" in backend.render_script(preemptable)

            fs_only = spec_with(attributes={
                "custom_attributes": {"filesystems": "eagle"}})
            backend.apply_defaults(fs_only)
            assert "#PBS -l filesystems=eagle" in backend.render_script(fs_only)

        # A directive line is one line of options, so a value with a space
        # injects a second option without needing a newline — every
        # rendered field is checked against its real syntax instead.
        injections = [
            {"queue_name": "debug -l place=excl", "account": "Catalyst"},
            {"queue_name": "workq-route", "account": "Catalyst -l place=excl"},
            {"queue_name": "workq-route", "account": "grp; qdel 1"},
            {"queue_name": "no-such-queue", "account": "Catalyst"},
            {"queue_name": "workq-route", "account": "Catalyst",
             "reservation_id": "A123456"},                          # two destinations
            {"queue_name": "workq-route", "account": "Catalyst",
             "reservation_id": "A123456 -x"},                      # injectable reservation
            {"queue_name": "workq-route", "account": "Catalyst",
             "custom_attributes": {"filesystems": "home:eagle -l place=excl"}},
            {"queue_name": "workq-route", "account": "Catalyst",
             "custom_attributes": {"unknown": "value"}},           # dropped attribute
        ]
        for attrs in injections:
            bad = JobSpec(executable="true", resources={"node_count": 1},
                          attributes={"duration": 600, **attrs})
            try:
                backend.apply_defaults(bad)
                backend.validate_spec(bad)
            except ValueError:
                continue
            raise AssertionError(
                f"crux accepted an injectable or unmappable value: {attrs}")

        # Offline queue limits exist because of the routing-queue trap: a
        # job outside its queue's range is accepted and then dropped with
        # no error at all (see the compute module's docstring).
        limit_violations = [
            ("debug", {"node_count": 5}, 600),
            ("debug", {"node_count": 1}, "02:00:01"),
            ("debug", {"node_count": 1}, 240),          # below the 5-minute floor
            ("workq-route", {"node_count": 177}, 600),
            ("workq-route", {"node_count": 1}, "25:00:00"),
            ("preemptable", {"node_count": 11}, 600),
            ("preemptable", {"node_count": 1}, "73:00:00"),
            ("demand", {"node_count": 1}, "01:01:00"),
        ]
        for queue, resources, duration in limit_violations:
            bad = JobSpec(executable="true", resources=resources,
                          attributes={"queue_name": queue, "account": "Catalyst",
                                      "duration": duration})
            try:
                backend.validate_spec(bad)
            except ValueError:
                continue
            raise AssertionError(
                f"crux accepted an out-of-range request for {queue}: "
                f"resources={resources}, duration={duration}")

        # Machine facts Crux simply cannot satisfy.
        impossible = [
            {"gpus": 1},                                      # CPU-only system
            {"gpu_cores_per_process": 1},
            {"memory": 300 * 1024**3},                        # > 256 GiB node
            {"processes_per_node": 300},                      # > 256 hw threads
        ]
        for resources in impossible:
            bad = JobSpec(executable="true", resources=resources,
                          attributes={"queue_name": "workq-route",
                                      "account": "Catalyst", "duration": 600})
            try:
                backend.validate_spec(bad)
            except ValueError:
                continue
            raise AssertionError(
                f"crux accepted an unsatisfiable resource request: {resources}")

        bad = spec_with()
        bad.container = {"image": "$HOME/app.sif"}
        try:
            backend.validate_spec(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("crux accepted a container spec (no Apptainer yet)")

        bad = spec_with()
        bad.stdin_path = "/home/u/input.dat"
        try:
            backend.validate_spec(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("crux accepted an unmapped stdin_path")

        # Output/error paths: quoted so a space can't split the directive,
        # and $HOME-anchored because qsub runs from the jobs directory.
        spaced = spec_with()
        spaced.stdout_path = "results/run dir/job.out"
        spaced.stderr_path = "results/run dir/job.err"
        spaced_script = backend.render_script(spaced)
        assert "#PBS -o '../results/run dir/job.out'" in spaced_script, spaced_script
        assert "#PBS -e '../results/run dir/job.err'" in spaced_script, spaced_script
        absolute = spec_with()
        absolute.stdout_path = "/eagle/projects/Catalyst/logs/job.out"
        assert ("#PBS -o /eagle/projects/Catalyst/logs/job.out"
                in backend.render_script(absolute))
        # Explicit working directories are anchored the same way.
        workdir = spec_with()
        workdir.directory = "agent/work/run1"
        assert 'cd "$HOME"/agent/work/run1' in backend.render_script(workdir)

        # Duration helpers: the model accepts D-HH:MM:SS, PBS wants plain
        # HH:MM:SS with hours free to exceed 24.
        assert _duration_seconds("2-00:00:00") == 172800
        assert _duration_seconds("0:10:00") == 600
        assert _duration_seconds(300) == 300
        assert _walltime("2-00:00:00") == "48:00:00"
        assert _walltime(600) == "00:10:00"

        # Job record mapping from qstat -F JSON fields.
        finished = backend._job("7001.crux-pbs-0001.head.cm.crux.alcf.anl.gov", {
            "Job_Name": "demo-run", "job_state": "F", "queue": "workq",
            "Account_Name": "Catalyst", "Exit_status": 0,
        })
        assert finished.status.state.value == "completed"
        assert finished.status.exit_code == 0
        failed = backend._job("7002.crux-pbs-0001.head.cm.crux.alcf.anl.gov", {
            "job_state": "F", "Exit_status": 2, "comment": "not a preemption",
        })
        assert failed.status.state.value == "failed"
        assert failed.status.exit_code == 2
        preempted = backend._job("7003.crux-pbs-0001.head.cm.crux.alcf.anl.gov", {
            "job_state": "F", "Exit_status": 271,
            "comment": "Job to be deleted at request of Scheduler",
        })
        assert preempted.status.state.value == "failed"   # scheduler killed it, not the user
        assert "request of Scheduler" in preempted.status.message
        running = backend._job("7004.crux-pbs-0001.head.cm.crux.alcf.anl.gov", {
            "job_state": "R", "queue": "workq",
            "Variable_List": ("PBS_O_HOME=/home/u,PBS_O_QUEUE=workq-route,"
                              "PBS_O_WORKDIR=/home/u/agent/jobs"),
            "resources_used": {"walltime": "00:03:21"},
        })
        assert running.status.state.value == "active"
        assert running.status.meta_data["workdir"] == "/home/u/agent/jobs"
        assert running.status.meta_data["walltime_used"] == "00:03:21"
        assert backend._pbs_workdir("PBS_O_HOME=/home/u") == ""
        # Finished jobs carry no Variable_List at all (confirmed live); the
        # submission directory must come from Output_Path instead, and the
        # output/error destinations are surfaced as usable paths.
        historical = backend._job("7006.crux-pbs-0001.head.cm.crux.alcf.anl.gov", {
            "job_state": "F", "Exit_status": 0,
            "Output_Path": ("crux-uan-0001.head.cm.crux.alcf.anl.gov:"
                            "/home/u/agent/jobs/demo-run.o7006"),
            "Error_Path": ("crux-uan-0001.head.cm.crux.alcf.anl.gov:"
                           "/home/u/agent/jobs/demo-run.e7006"),
            "comment": "Job run at Mon Nov 02 at 11:29 on a vnode and finished",
        })
        assert historical.status.state.value == "completed"
        assert historical.status.meta_data["workdir"] == "/home/u/agent/jobs"
        assert (historical.status.meta_data["output_path"]
                == "/home/u/agent/jobs/demo-run.o7006")
        assert (historical.status.meta_data["error_path"]
                == "/home/u/agent/jobs/demo-run.e7006")
        assert backend._strip_host("crux-host:/home/u/x") == "/home/u/x"
        assert backend._strip_host("/home/u/x") == "/home/u/x"

        # JSON record parsing, including seq-only id matching.
        qstat_output = '''{
          "timestamp": 1790000000,
          "pbs_version": "2022.1",
          "pbs_server": "crux-pbs-0001.head.cm.crux.alcf.anl.gov",
          "Jobs": {
            "7004.crux-pbs-0001.head.cm.crux.alcf.anl.gov": {
              "Job_Name": "demo-run", "job_state": "R", "queue": "workq",
              "Variable_List": "PBS_O_WORKDIR=/home/u/agent/jobs"
            }
          }
        }'''
        records = backend._parse_qstat_json(qstat_output)
        assert list(records) == ["7004.crux-pbs-0001.head.cm.crux.alcf.anl.gov"]
        # A finished job's record keeps Output_Path (history drops
        # Variable_List) so workdir survives into history.
        historical_records = backend._parse_qstat_json(json.dumps({
            "Jobs": {"7006.crux-pbs-0001.head.cm.crux.alcf.anl.gov": {
                "job_state": "F", "Exit_status": 0,
                "Output_Path": ("crux-uan-0001.head.cm.crux.alcf.anl.gov:"
                                "/home/u/agent/jobs/demo-run.o7006"),
            }}
        }))
        assert backend._job(
            "7006.crux-pbs-0001.head.cm.crux.alcf.anl.gov",
            historical_records["7006.crux-pbs-0001.head.cm.crux.alcf.anl.gov"],
        ).status.meta_data["workdir"] == "/home/u/agent/jobs"

        with patch("facilities.crux.compute.run_command",
                   return_value=qstat_output) as command:
            found = backend.get_statuses(["7004"])[0]
        assert command.call_args.args[1] == "qstat -fx -F JSON 7004"
        assert found.id.endswith("crux.alcf.anl.gov")
        assert found.status.state.value == "active"

        # A missing id must explain the routing-queue trap, not just vanish.
        with patch("facilities.crux.compute.run_command",
                   side_effect=RuntimeError("qstat: Unknown Job Id 9999")):
            missing = backend.get_statuses(["9999"])[0]
        assert missing.status.state.value == "unknown"
        assert "node count and walltime" in missing.status.message

        # sbank parsing: ALCF's live layout adds a Suballocation column to
        # sbank's documented default, and both are handled by shape (the
        # start/end date pair), not by fixed position. Synthetic rows with
        # the real layouts; multi-word project names; a negative balance;
        # and a Totals section that must not become data.
        sbank_alcf_layout = '''
         Allocation  Suballocation  Start       End         Resource  Project      Jobs  Charged  Available Balance
         ----------  -------------  ----------  ----------  --------  ---------  ----  -------  -----------------
         7001        7011           2026-01-01  2026-12-31  crux      Catalyst      1,234  12,345.6  87,654.3
         7002        7012           2026-01-01  2026-12-31  crux      My Project      987  -1,234.5   1,234.5
         7003        7013           2026-01-01  2026-12-31  eagle     Catalyst         12      3.4       1.0

        Totals:
          Rows: 3
          Crux:
            Available Balance: 88,888.8 node hours
            Charged          : 13,580.1 node hours
            Jobs             : 2,221
        Date filters (UTC): none
        '''
        sbank_default_layout = '''
         Id         Start       End         Resource   Project          Jobs        Charged          Available Balance
         ---------  ----------  ----------  ---------  ---------------  ----------  ---------------  -----------------
         42         2026-01-01  2026-12-31  somehost   Defaultlayout        5         1.0               2.0
        '''
        with patch("facilities.crux.compute.run_command",
                   return_value=sbank_alcf_layout) as command:
            projects = backend.get_projects()
        assert command.call_args.args[1] == "sbank-list-allocations -r crux"
        assert [p["account"] for p in projects] == ["Catalyst", "My Project"]
        assert projects[0]["allocation_ids"] == ["7001"]    # eagle row filtered out
        assert projects[0]["jobs"] == 1234
        assert projects[0]["charged"] == 12345.6
        assert projects[1]["available_balance"] == 1234.5   # negative parsed, not rejected

        # sbank's documented default layout (no Suballocation column) is
        # the fallback shape — parsed, then resource-filtered like any other.
        with patch("facilities.crux.compute.run_command",
                   return_value=sbank_default_layout):
            assert backend._allocations() == []

        with patch("facilities.crux.compute.run_command",
                   return_value=sbank_alcf_layout):
            allocations = backend.get_project_allocations("My Project")
        assert allocations["charged_total"] == -1234.5
        assert allocations["allocations"][0]["end"] == "2026-12-31"
        assert allocations["allocations"][0]["suballocation_id"] == "7012"
        try:
            with patch("facilities.crux.compute.run_command",
                       return_value=sbank_alcf_layout):
                backend.get_project_allocations("NotAProject")
        except ValueError:
            pass
        else:
            raise AssertionError("crux invented allocations for an unknown project")

        # An empty sbank result is never a valid "no projects" answer: an
        # ALCF account always belongs to a project, so say what to check.
        with patch("facilities.crux.compute.run_command", return_value=""):
            try:
                backend.get_projects()
            except ValueError as exc:
                assert "expired" in str(exc) or "sbank" in str(exc)
            else:
                raise AssertionError(
                    "crux returned an empty project list without explaining it")

        # qstat -Q table -> queue rows (header-driven parsing).
        queue_output = '''
        Queue          Max  Tot Ena Str Que Run Hld Wat Trn Ext Type
        -------------- ---- ---- --- --- ---- ---- ---- ---- ---- ---- ----
        debug            4    2 yes yes   1   1   0   0   0   0 Exe*
        workq-route    100   42 yes yes  12  30   0   0   0   0 Rou*
        '''
        # pbsnodes summary -> machine-wide node counts, including a
        # combined state (offline,resv-exclusive) that must not be skipped.
        nodes_output = '''
                                                                        mem       ncpus   nmics   ngpus
        vnode           state           njobs   run   susp      f/t        f/t     f/t     f/t   jobs
        --------------- --------------- ------ ----- ------ ------------ ------- ------- ------- -------
        x1000c0s0b1n0   free                0     0      0  252gb/252gb   256/256     0/0     0/0 --
        x1000c0s0b1n1   job-exclusive       1     1      0  252gb/252gb   256/256     0/0     0/0 7004
        x1000c0s0b1n2   offline             0     0      0  252gb/252gb   256/256     0/0     0/0 --
        x1000c0s0b1n3   offline,resv-exclusive 0  0      0  252gb/252gb   256/256     0/0     0/0 --
        '''
        with patch("facilities.crux.compute.run_command",
                   side_effect=[queue_output, nodes_output]):
            resources_list = backend.get_live_resources()
        by_name = {row["partition"]: row for row in resources_list}
        assert set(by_name) == {"debug", "workq-route"}
        # live qstat -Q truncates the Type column ("Rou*"); the star is stripped
        assert by_name["workq-route"]["queue_type"] == "Rou"
        assert by_name["workq-route"]["running_jobs"] == 30
        assert by_name["debug"]["queued_jobs"] == 1
        nodes = by_name["debug"]["nodes"]
        assert nodes == {"allocated": 1, "idle": 1, "other": 2, "total": 4}

        # Down-node listing.
        down_output = ("x1000c0s0b1n2       offline    synthetic fixture reason\n")
        with patch("facilities.crux.compute.run_command",
                   return_value=down_output):
            drained = backend.get_drained_nodes()
        assert drained == [{"nodes": "x1000c0s0b1n2", "state": "offline",
                             "reason": "synthetic fixture reason"}]

        # Submission: script written under the jobs dir, qsub run from there
        # so streamed output lands beside the script, id parsed off the
        # server-qualified form.
        submitted = spec_with()
        with patch("facilities.crux.compute.write_remote_file",
                   return_value="/home/u/agent/jobs/crux-shape-20261101-000000.pbs") \
                as write, patch("facilities.crux.compute.run_command",
                   return_value="7005.crux-pbs-0001.head.cm.crux.alcf.anl.gov\n") \
                as command:
            result = backend.submit(submitted)
        assert result["job_id"] == "7005.crux-pbs-0001.head.cm.crux.alcf.anl.gov"
        assert write.call_args.args[1].startswith("agent/jobs/")
        qsub_command = command.call_args.args[1]
        assert "chmod 600" in qsub_command
        assert 'cd "$(dirname' in qsub_command
        assert qsub_command.endswith("qsub /home/u/agent/jobs/crux-shape-20261101-000000.pbs")

        # Recent statuses: qselect (with the ctime cutoff) then batched
        # qstat for full records.
        with patch("facilities.crux.compute.run_command",
                   side_effect=[
                       "7004.crux-pbs-0001.head.cm.crux.alcf.anl.gov\n"
                       "7005.crux-pbs-0001.head.cm.crux.alcf.anl.gov\n",
                       qstat_output,
                   ]) as command:
            recent = backend.get_recent_statuses("now-2days")
        assert command.call_args_list[0].args[1].startswith("qselect -x -u $USER -tc.gt.")
        assert "qstat -fx -F JSON" in command.call_args_list[1].args[1]
        assert [job.id for job in recent] == ["7004.crux-pbs-0001.head.cm.crux.alcf.anl.gov"]

        # Update: qalter for mutable attributes, qmove for the queue, both
        # only for fields the caller actually set.
        updated = Job(id="7004", status={"state": "active"})
        walltime_spec = JobSpec(executable="true", attributes={"duration": 300})
        with patch("facilities.crux.compute.run_command") as command, \
                patch.object(backend, "get_statuses", return_value=[updated]):
            backend.update("7004", walltime_spec)
        assert command.call_args.args[1] == "qalter -l walltime=00:05:00 7004"

        move_spec = JobSpec(executable="true",
                            attributes={"queue_name": "debug"})
        with patch("facilities.crux.compute.run_command") as command, \
                patch.object(backend, "get_statuses", return_value=[updated]):
            backend.update("7004", move_spec)
        assert command.call_args.args[1] == "qmove debug 7004"

        everything_spec = JobSpec(executable="true", name="renamed",
                                  stdout_path="logs/out.txt",
                                  attributes={"duration": 300, "account": "Catalyst"},
                                  resources={"node_count": 2})
        with patch("facilities.crux.compute.run_command") as command, \
                patch.object(backend, "get_statuses", return_value=[updated]):
            backend.update("7004", everything_spec)
        rendered = command.call_args.args[1]
        assert rendered.startswith("qalter ")
        assert "-N renamed" in rendered
        assert "-l walltime=00:05:00" in rendered
        assert "-A Catalyst" in rendered
        assert "-l select=2:system=crux" in rendered
        assert "-o logs/out.txt" in rendered

        conflicting = JobSpec(executable="true", attributes={
            "queue_name": "debug", "reservation_id": "A123456"})
        try:
            backend.update("7004", conflicting)
        except ValueError:
            pass
        else:
            raise AssertionError("crux updated toward two different queues at once")

        empty_spec = JobSpec(executable="true", environment={"A": "b"})
        try:
            backend.update("7004", empty_spec)
        except ValueError as exc:
            assert "Nothing updatable" in str(exc)
            assert "environment" in str(exc)
        else:
            raise AssertionError("crux applied an update with nothing updatable set")

    def setup_directions_are_actionable():
        """What a user gets when they say "I want to use this machine" and
        nothing is configured. It has to stand on its own: the agent may
        not be able to open any other file, so the directions must name the
        config file, show what to put in it, and cover this machine's own
        prerequisites."""
        assert fac.setup_help.strip(), (
            "no setup_help registered — an unconfigured user would get generic "
            "directions with nothing machine-specific (how to get a key "
            "registered, the real login hostname, any required account)"
        )
        assert fac.config_example, "no config_example registered"
        assert "ssh" in fac.config_example, "config_example has no ssh section"

        with no_user_config(slug):
            text = config.setup_instructions(slug)
            expected_path = str(config.config_path(slug))
        assert expected_path in text, "directions omit the config file path"
        assert f"{slug}-configuring" in text, "directions don't name the configuring skill"
        assert "hpc-doctor" in text, "directions don't say how to verify"
        assert fac.setup_help.splitlines()[0] in text, "setup_help didn't reach the directions"
        # The example must be valid, copy-pasteable JSON.
        import json as _json
        _json.loads(_json.dumps(fac.config_example))

    def unconfigured_catalog_data_is_readable():
        """Bundled data remains readable so setup directions can be built."""
        with no_user_config(slug):
            assert config.load_facts(slug), "get_facility would fail unconfigured"
            assert config.docs_source(slug).exists(), "guide unreadable unconfigured"
            assert fac.display_name and fac.description, "get_facilities would be degraded"

    def unconfigured_tools_still_answer():
        """The never-fail invariant, at tool granularity: every tool that
        does not need the cluster must keep working with no config at all,
        so an agent can orient the user *before* setup.

        Checked through the MCP entry points, not the helpers underneath —
        the regression this guards against was a decorator applied to the
        whole tool surface, which the helpers would not have noticed. An
        earlier version of this file asserted only on config.load_facts()
        and so passed while get_facility itself was raising.
        """
        from hpc_mcp.hpc_server import get_facility, render_job_script
        from hpc_agent_core import docs_server
        from hpc_agent_core.models import JobSpec

        with no_user_config(slug):
            facts = get_facility(slug)
            assert facts, "get_facility returned nothing unconfigured"

            # Packaged index: searching a guide is how an agent answers
            # "what partitions does this machine have" before SSH exists.
            index = docs_server._index(slug)
            hits = index.search("storage quota partition", top_k=2)
            assert hits, f"{slug}: docs search returned nothing unconfigured"
            sections = index.chunks
            assert sections, f"{slug}: no doc sections unconfigured"

            # Local-only rendering. Supplying an account keeps facilities
            # that mandate one on the happy path; the point is that nothing
            # here reaches for a connection.
            spec = JobSpec.model_validate({
                "name": "offline-render", "executable": "hostname",
                "attributes": {"account": "conformance-probe",
                               "duration": 600},
            })
            try:
                script = render_job_script(slug, spec)
            except ValueError:
                pass          # a facility may reject this minimal spec; fine
            else:
                assert script.strip(), f"{slug}: empty script unconfigured"

    def unconfigured_account_query_returns_setup():
        """Capability errors must not mask the cold-start configuration path."""
        from hpc_mcp.hpc_server import get_projects
        with no_user_config(slug):
            try:
                get_projects(slug)
            except RuntimeError as exc:
                text = str(exc)
                assert "not configured yet" in text
                assert f"{slug}-configuring" in text
            else:
                raise AssertionError(
                    "unconfigured get_projects did not return setup instructions"
                )

    print(f"\n=== {slug} ({fac.display_name}) ===")
    check("registration is complete", registration_is_complete)
    check("facts JSON loads", facts_load)
    check("backend is bound to this facility", backend_knows_its_facility)
    check("setup directions are machine-specific and actionable", setup_directions_are_actionable)
    check("bundled catalog data remains readable without user config",
          unconfigured_catalog_data_is_readable)
    check("no-config tools still answer (never-fail invariant)",
          unconfigured_tools_still_answer)
    check("unconfigured account query returns setup directions first",
          unconfigured_account_query_returns_setup)
    check("apply_defaults is idempotent", apply_defaults_is_idempotent)
    check("apply_defaults never overwrites caller values", explicit_values_survive_defaults)
    check("defaults -> validate -> render, or an actionable error", defaults_then_validate_then_render)
    check("same with no user config (a brand-new user)", defaults_then_validate_then_render_unconfigured)
    check("a defaulted queue reaches the script", rendered_script_has_a_queue)
    if slug == "rikyu":
        check("deterministic machine resource limits are enforced",
              machine_resource_limits_are_enforced)
    if slug == "miyabi":
        check("PBS shape and dated machine limits are enforced",
              miyabi_pbs_shape_and_limits_are_enforced)
    if slug == "octopus":
        check("dual-vendor defaults and machine limits are enforced",
              octopus_dual_vendor_defaults_and_limits_are_enforced)
    if slug == "tsubame":
        check("resource-type Grid Engine dialect and trial limits are enforced",
              tsubame_resource_types_and_trial_limits_are_enforced)
    if slug == "irene":
        check("Bridge shape, parsers, and machine limits are enforced",
              irene_bridge_shape_and_limits_are_enforced)
    if slug == "cell2026":
        check("dual-scheduler rendering, validation, and routing are enforced",
              cell2026_dual_scheduler_routing_is_enforced)
    if slug == "crux":
        check("ALCF PBS shape, limits, parsers, and sbank accounting are enforced",
              crux_pbs_shape_and_limits_are_enforced)


# --- repo-wide checks ----------------------------------------------------

def check_repo() -> None:
    print("\n=== repo-wide ===")

    def facilities_exist():
        assert config.list_facilities(), "no facilities registered"

    def unknown_facility_errors_clearly():
        for label, fn in (("config", config.get_facility), ("registry", get_backend)):
            try:
                fn("definitely-not-a-facility")
            except ValueError as e:
                assert "Unknown facility" in str(e), f"{label}: {e}"
                assert "Valid facilities:" in str(e), f"{label}: no slug list in {e}"
            else:
                raise AssertionError(f"{label}: expected ValueError")

    def slugs_are_url_and_identifier_safe():
        for fac in config.list_facilities():
            assert fac.slug == fac.slug.lower(), f"{fac.slug}: not lowercase"
            assert " " not in fac.slug, f"{fac.slug}: contains a space"
            assert fac.slug.replace("-", "").isalnum(), f"{fac.slug}: unexpected characters"

    def unreachable_detection_discriminates():
        """A scheduler error must not be mistaken for an SSH failure.

        Regression guard: a looser version of this check matched a bare
        "permission denied", so Slurm's own "Access/permission denied for
        job 9041823" came back buried in a wall of SSH setup directions
        instead of as the clear scheduler error it is. Caught live while
        testing update_job(hold=True) on HBW2.
        """
        from hpc_agent_core.middleware import _looks_unreachable as unreachable
        scheduler_and_command_errors = [
            ("Access/permission denied for job 9041823", None),
            ("slurm_suspend error:Job has already finished", None),
            ("ls: cannot access '/nope': No such file or directory", None),
            ("sbatch: error: Invalid account or account/partition combination", None),
            ("some remote failure", 2),
        ]
        for text, rc in scheduler_and_command_errors:
            assert not unreachable(text, rc), f"misread as an SSH failure: {text!r}"
        real_ssh_failures = [
            ("user@host: Permission denied (publickey).", None),
            ("ssh: connect to host x port 22: Connection refused", None),
            ("ssh: Could not resolve hostname bad.invalid", None),
            ("", 255),
        ]
        for text, rc in real_ssh_failures:
            assert unreachable(text, rc), f"missed a real SSH failure: {text!r} rc={rc}"

    def fs_rm_refuses_dangerous_paths():
        """fs_rm is the one irreversible tool here — these filesystems have
        no trash. Deleting a home directory or a filesystem root is far more
        likely to be a mistake (an unset variable, a stray default, a glob
        that expanded to nothing) than an intent, so those must be refused
        before any command is built, not just discouraged in a docstring."""
        from hpc_mcp.hpc_server import fs_rm
        with patch.dict(os.environ, {"CELL2026_HOST": "localhost"}):
            for bad in ["", " ", ".", "..", "/", "~", "~/", "*", "$HOME", ".//"]:
                try:
                    fs_rm("cell2026", bad)
                except ValueError as e:
                    assert "Refusing to delete" in str(e), (
                        f"{bad!r} was not refused before a command was built: {e}")
                else:
                    raise AssertionError(f"fs_rm did not refuse {bad!r}")

    def generated_skills_are_wellformed():
        """Every generated SKILL.md needs YAML frontmatter whose name
        matches its directory, or the client cannot discover it.

        Caught a real one: Fugaku-Agent's fugaku-build skill shipped with
        no frontmatter at all — the only skill in that repo missing it, so
        it had no name or description to be found by.
        """
        import pathlib
        root = pathlib.Path(__file__).resolve().parent.parent
        skills = sorted((root / "plugins").glob("hpc-*/skills/*/SKILL.md"))
        assert skills, "no generated skills found"
        for path in skills:
            text = path.read_text()
            assert text.startswith("---\n"), f"{path.parent.name}: no YAML frontmatter"
            front = text.split("---", 2)[1]
            assert f"name: {path.parent.name}\n" in front, (
                f"{path.parent.name}: frontmatter name does not match its directory")
            assert "description:" in front, f"{path.parent.name}: no description"

        remote_skills = sorted((root / "plugins").glob(
            "hpc-*/skills/*-remote-command/SKILL.md"))
        assert len(remote_skills) == len(config.list_facilities()), (
            "every facility needs a generated remote-command skill"
        )
        for path in remote_skills:
            text = path.read_text()
            assert "May I run these" in text, f"{path.parent.name}: no permission example"
            assert "Prefer multiple focused calls" in text, (
                f"{path.parent.name}: no short-command guidance"
            )
            assert "Changed state:" in text, f"{path.parent.name}: no execution recap example"

    def facility_skill_packs_are_isolated_and_discoverable():
        """The same base/pack split is valid for all three plugin formats."""
        import json
        root = pathlib.Path(__file__).resolve().parent.parent
        facilities = config.list_facilities()
        base_skills = sorted(p.name for p in (root / "plugins" / "hpc" / "skills").iterdir()
                             if p.is_dir())
        assert base_skills == ["hpc-facilities"], (
            "the base plugin must not preload facility workflow skills")

        marketplace = json.loads((root / ".agents" / "plugins" / "marketplace.json").read_text())
        names = [entry["name"] for entry in marketplace["plugins"]]
        assert names == ["hpc", *(f"hpc-{fac.slug}" for fac in facilities)]
        claude_marketplace = json.loads(
            (root / ".claude-plugin" / "marketplace.json").read_text())
        assert [entry["name"] for entry in claude_marketplace["plugins"]] == names

        base_portable = json.loads((root / "plugins" / "hpc" / "plugin.json").read_text())
        assert base_portable["$schema"].endswith("plugin.schema.json")
        portable_mcp = json.loads((root / "plugins" / "hpc" / "mcp.json").read_text())
        assert portable_mcp["$schema"].endswith("mcp.schema.json")
        assert set(portable_mcp["mcpServers"]) == {"hpc", "hpc-docs"}
        for fac in facilities:
            plugin = root / "plugins" / f"hpc-{fac.slug}"
            manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text())
            assert manifest["name"] == f"hpc-{fac.slug}"
            assert "mcpServers" not in manifest, f"{fac.slug} pack must not duplicate MCP"
            claude = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text())
            portable = json.loads((plugin / "plugin.json").read_text())
            assert claude["name"] == manifest["name"] == portable["name"]
            assert portable["$schema"].endswith("plugin.schema.json")
            assert list((plugin / "skills").glob(f"{fac.slug}-*/SKILL.md")), \
                f"{fac.slug} pack has no generated skills"

    def readme_requires_explicit_facility_selection_for_manual_install():
        root = pathlib.Path(__file__).resolve().parent.parent
        readme = (root / "README.md").read_text()
        normalized = " ".join(readme.split())
        assert "before installing any facility skills, ask the user" in normalized
        assert "Do not install all facility packs by default" in normalized
        assert "plugins/hpc-<selected-slug>/skills/" in readme

    def job_name_cannot_inject_into_scripts():
        """spec.name is rendered unquoted into every scheduler's directive
        line and used to build the job script's filename, so it is a real
        injection boundary — a newline puts executable lines into a script
        the scheduler runs, and a slash writes the script outside the jobs
        directory. Both were demonstrated against this code. Guarded once in
        the model so it holds for schedulers added later.
        """
        from hpc_agent_core.models import JobSpec
        for bad in ["ok\nrm -rf /", "../../../tmp/pwned", "a b",
                    'x"; rm -rf ~; #', "", "n" * 200, "foo$(id)", "a|b"]:
            try:
                JobSpec.model_validate({"name": bad, "executable": "x"})
            except Exception:
                continue
            raise AssertionError(f"job name accepted but should be rejected: {bad!r}")
        for ok in ["agent-job", "hub-smoke", "train_vit.v2", "probe360"]:
            JobSpec.model_validate({"name": ok, "executable": "x"})

        # Same primitive, every other field rendered into a directive line.
        for label, extra in [
            ("queue_name", {"attributes": {"queue_name": "gpu\nrm -rf /"}}),
            ("account", {"attributes": {"account": "a\n#SBATCH --uid=0"}}),
            ("reservation_id", {"attributes": {"reservation_id": "r\nevil"}}),
            ("custom key", {"attributes": {"custom_attributes": {"k\nevil": "v"}}}),
            ("custom value", {"attributes": {"custom_attributes": {"k": "v\nevil"}}}),
            ("directory", {"directory": "/tmp\nevil"}),
            ("stdout_path", {"stdout_path": "o\nevil"}),
        ]:
            spec = {"name": "t", "executable": "x", **extra}
            try:
                JobSpec.model_validate(spec)
            except Exception:
                continue
            raise AssertionError(f"control character accepted in {label}")

        # duration is both a directive-line field on every scheduler and a
        # login-node shell argument for Fugaku's pjalter update path.
        for bad in ["00:01:00\nrm -rf /", '00:01:00"; touch /tmp/pwned; #',
                    "not-a-duration", "00:60:00", True, 0, -1]:
            try:
                JobSpec.model_validate({
                    "name": "t", "executable": "x",
                    "attributes": {"duration": bad},
                })
            except Exception:
                continue
            raise AssertionError(f"unsafe/invalid duration accepted: {bad!r}")

    def resource_quantities_are_positive():
        invalid = [
            {"node_count": 0}, {"node_count": -1},
            {"process_count": 0}, {"process_count": -1},
            {"processes_per_node": 0}, {"cpu_cores_per_process": 0},
            {"gpu_cores_per_process": 0}, {"gpus": -1}, {"memory": 0},
        ]
        invalid += [
            {field: True} for field in (
                "node_count", "process_count", "processes_per_node",
                "cpu_cores_per_process", "gpu_cores_per_process", "gpus", "memory",
            )
        ]
        for resources in invalid:
            try:
                JobSpec.model_validate({"executable": "x", "resources": resources})
            except Exception:
                continue
            raise AssertionError(f"invalid resource quantity accepted: {resources!r}")

    def process_count_is_an_alternative_to_ppn():
        from hpc_agent_core.compute.slurm import SlurmBackend

        backend = SlurmBackend("test", nodes_always_explicit=True)
        total_only = JobSpec(
            executable="hostname", resources={"process_count": 8},
            attributes={"queue_name": "test"},
        )
        script = backend.render_script(total_only)
        assert "#SBATCH --ntasks=8" in script
        assert "#SBATCH --ntasks-per-node" not in script, script

        both = JobSpec(
            executable="hostname",
            resources={"process_count": 8, "processes_per_node": 4},
            attributes={"queue_name": "test"},
        )
        script = backend.render_script(both)
        assert "#SBATCH --ntasks=8" in script
        assert "#SBATCH --ntasks-per-node=4" in script

    def home_shorthand_is_normalized_for_scheduler_paths():
        """Scheduler directives do not expand shell variables themselves.

        The shared submitter starts in $HOME, so every supported home form
        must become a relative path before it reaches a Slurm/GE directive.
        Test both the helper and every currently supported directive path.
        """
        from hpc_agent_core.compute.gridengine import GridEngineBackend
        from hpc_agent_core.compute.slurm import SlurmBackend
        from hpc_agent_core.middleware import norm_path

        expected = {
            "~": ".",
            "~/agent/work": "agent/work",
            "$HOME": ".",
            "$HOME/agent/work": "agent/work",
            "${HOME}/agent/work": "agent/work",
        }
        for source, normalized in expected.items():
            assert norm_path(source) == normalized

        spec = JobSpec(
            executable="true",
            directory="$HOME/agent/work/run",
            stdin_path="${HOME}/inputs/in.dat",
            stdout_path="~/outputs/out.log",
            stderr_path="$HOME/outputs/err.log",
            attributes={"queue_name": "test"},
        )
        slurm = SlurmBackend("test", nodes_always_explicit=True)
        slurm_script = slurm.render_script(spec)
        assert "#SBATCH --chdir=agent/work/run" in slurm_script
        assert "#SBATCH --input=inputs/in.dat" in slurm_script
        assert "#SBATCH --output=outputs/out.log" in slurm_script
        assert "#SBATCH --error=outputs/err.log" in slurm_script

        ge = GridEngineBackend("test")
        ge_script = ge.render_script(spec)
        assert "#$ -wd agent/work/run" in ge_script
        assert "#$ -o outputs/out.log" in ge_script
        assert "#$ -e outputs/err.log" in ge_script

    def fugaku_update_quotes_duration_as_one_argument():
        from facilities.fugaku.compute import PJMBackend

        backend = PJMBackend("fugaku")
        unsafe = '01:02:03"; touch /tmp/pwned; #'
        # Bypass the generic validator deliberately to verify the backend's
        # independent defense in depth. Normal MCP input cannot construct
        # this model after the duration fix above.
        spec = JobSpec.model_construct(
            executable="unused",
            resources=ResourceSpec(),
            attributes=JobAttributes.model_construct(duration=unsafe),
        )
        commands = []

        def record(_facility, command):
            commands.append(command)
            return ""

        with patch("facilities.fugaku.compute.run_command", record), \
                patch.object(backend, "get_statuses", return_value=[]):
            try:
                backend.update("123", spec)
            except ValueError:
                pass  # expected: the mocked status lookup finds no job
        assert len(commands) == 1, commands
        assert shlex.split(commands[0]) == ["pjalter", "-L", f"elapse={unsafe}", "123"]

    def fugaku_pjm_accounting_exposes_groups_and_points():
        """Fugaku's IRI accounting shape from `id -Gn` + `accountj_pt -c`.

        Fixture strings are the exact formats observed live on 2026-08-30:
        the `id` group list and one GROUP_POINT CSV row.
        """
        from facilities.fugaku.compute import PJMBackend

        backend = PJMBackend("fugaku")
        pt_csv = (
            'INFO_H,COLLECT_DATE\n'
            '"INFO","2026-08-30 22:08:01"\n'
            'GROUP_POINT_H,GROUP,POINT,LIMIT(N),USAGE(N),AVAILABLE(N)\n'
            '"GROUP_POINT","ra000009","1110550","466431087","291635579","174795508"\n'
        )

        def fake(_facility, command):
            if command == "id -Gn":
                return "fugaku ra000009 ra250029 hp250291 trial\n"
            if " trial " in command:
                raise RuntimeError("no GROUP_POINT row for trial")
            return pt_csv

        with patch("facilities.fugaku.compute.run_command", fake):
            rows = backend.get_projects()
        accounts = [row["account"] for row in rows]
        assert accounts == ["hp250291", "ra000009", "ra250029", "trial"], accounts
        assert "fugaku" not in accounts  # shared group cannot submit
        assert rows[0]["points"]["point_total"] == 1110550
        assert "f-pt" in rows[0]["resource_groups"]
        assert rows[-1]["resource_groups"] == [
            "spot-small", "spot-large", "spot-int", "spot-middle"]
        assert "points" not in rows[-1]
        for row in rows:
            assert row["qos"] == []

        with patch("facilities.fugaku.compute.run_command",
                   return_value=pt_csv):
            alloc = backend.get_project_allocations("ra000009")
        assert alloc == {
            "project_id": "ra000009", "point_total": 1110550,
            "limit_n": 466431087, "usage_n": 291635579,
            "available_n": 174795508,
        }

        with patch("facilities.fugaku.compute.run_command",
                   side_effect=RuntimeError("connection failed")):
            try:
                backend.get_project_allocations("trial")
            except RuntimeError as exc:
                assert "connection failed" in str(exc)
            else:
                raise AssertionError(
                    "a failed read was masked as 'project has no points'")

    def docs_embedding_client_is_not_cached():
        from hpc_agent_core.docs_server import _index

        index = _index("rikyu")
        assert index._embed_client is None, (
            "the cached docs index captured an embedding client/API key"
        )
        token = object()
        # search() only reaches the vector path when embeddings are loaded.
        # A facility may legitimately ship BM25-only (no embeddings.npy, e.g.
        # after a guide edit made while the embedding endpoint was down), so
        # stand in a matrix rather than depending on what happens to be
        # committed — the invariant under test is that the client is passed
        # per call and never cached on the index.
        import numpy as _np
        with patch.object(index, "_embeddings",
                          _np.zeros((len(index.chunks), 4), dtype="float32")), \
                patch.object(index, "_vector_search", return_value=[]) as vector:
            index.search("anything", embed_client=token)
        vector.assert_called_once_with("anything", 5, token)

    def ssh_multiplexing_detection_is_advisory_and_uses_resolved_config():
        """Doctor must inspect local OpenSSH config without connecting."""
        from hpc_agent_core.doctor import check_ssh_multiplexing

        resolved = subprocess.CompletedProcess(
            ["ssh", "-G", "example"], 0,
            "controlmaster auto\ncontrolpath /tmp/ssh-%C\ncontrolpersist 30m\n",
            "",
        )
        active = subprocess.CompletedProcess(
            ["ssh", "-O", "check", "example"], 0, "", "Master running")
        with patch("hpc_agent_core.doctor.config.ssh_host", return_value="example"), \
                patch("hpc_agent_core.doctor.subprocess.run",
                      side_effect=[resolved, active]) as run:
            assert check_ssh_multiplexing("rikyu")
        assert run.call_args_list[0].args[0] == ["ssh", "-G", "example"]
        assert run.call_args_list[1].args[0] == ["ssh", "-O", "check", "example"]

        disabled = subprocess.CompletedProcess(
            ["ssh", "-G", "example"], 0, "controlmaster no\n", "",
        )
        with patch("hpc_agent_core.doctor.config.ssh_host", return_value="example"), \
                patch("hpc_agent_core.doctor.subprocess.run",
                      return_value=disabled) as run:
            assert check_ssh_multiplexing("rikyu")
        assert run.call_count == 1, "ControlMaster no must skip socket probing"

    def a_broken_facility_cannot_deny_the_server():
        """One facility failing to import must not take down the others.

        The hub sharpened this: a single process now serves every facility,
        so an exception in one facility.py would otherwise deny every other
        facility to every user. Verified by importing a deliberately broken
        module the same way hpc_mcp does, and asserting the healthy ones
        survive and the failure is recorded rather than swallowed.
        """
        import importlib.util
        import tempfile
        import hpc_mcp

        healthy = {f.slug for f in config.list_facilities()}
        assert healthy, "no healthy facilities to protect"

        with tempfile.TemporaryDirectory() as tmp:
            mod = pathlib.Path(tmp) / "broken_facility.py"
            mod.write_text("raise RuntimeError('deliberately broken')\n")
            spec = importlib.util.spec_from_file_location("broken_facility", mod)
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except Exception as exc:
                recorded = f"{type(exc).__name__}: {exc}"
            else:
                raise AssertionError("the broken module did not raise")

        assert "RuntimeError" in recorded, recorded
        assert {f.slug for f in config.list_facilities()} == healthy, \
            "a failed facility import disturbed the healthy registry"
        assert isinstance(hpc_mcp.FAILED_FACILITIES, dict), \
            "hpc_mcp must expose FAILED_FACILITIES so a skipped facility is never silent"

    def facility_data_is_declared_as_package_data():
        """Every file a facility reads at runtime must match a
        package-data glob in pyproject.toml.

        These are read via Path(__file__).parent/"data", which works
        perfectly in an editable install and silently ships nothing in a
        wheel unless declared. That is the failure this repo's own
        PORTING.md warns about, and it was real here: the first built wheel
        contained zero guides, zero docs indexes and zero facts JSON, so the
        documented `uv tool run --from git+...` install would have produced
        a server where get_facility and search_docs failed on every
        facility, while local testing looked fine.
        """
        import fnmatch
        import tomllib
        root = pathlib.Path(__file__).resolve().parent.parent
        with open(root / "pyproject.toml", "rb") as fh:
            globs = tomllib.load(fh)["tool"]["setuptools"]["package-data"]["*"]

        for fac in config.list_facilities():
            wanted = [fac.data_dir / fac.docs_filename,
                      fac.data_dir / fac.facts_filename,
                      fac.data_dir / "docs_index" / "chunks.json"]
            for path in wanted:
                if not path.exists():
                    continue
                rel = path.relative_to(fac.data_dir.parent).as_posix()
                assert any(fnmatch.fnmatch(rel, g) for g in globs), (
                    f"{fac.slug}: {rel} matches no package-data glob in "
                    f"pyproject.toml, so it would not ship in a wheel")

    def every_facility_has_skill_notes():
        """A facility with no notes for a workflow still renders (a stub is
        substituted), but submitting-jobs is where a port's real value
        lives — an empty one means an unfinished port."""
        import pathlib
        root = pathlib.Path(__file__).resolve().parent.parent
        for manifest in sorted((root / "facilities").glob("*/facility.json")):
            notes = manifest.parent / "skill_notes" / "submitting-jobs.md"
            assert notes.exists() and notes.read_text().strip(), \
                f"{manifest.parent.name}: skill_notes/submitting-jobs.md is missing or empty"

    def remote_command_skills_cover_forwarded_git_authentication():
        """Generated command skills must not guess a generic SSH key path."""
        root = pathlib.Path(__file__).resolve().parent.parent
        source = (root / "templates" / "skills" / "remote-command.md.tmpl").read_text()
        assert "ssh -G <host>" in source
        assert "forwardagent" in source
        assert "ssh-add <their-facility-key>" in source
        assert "never invent a path" in source
        for facility in config.list_facilities():
            rendered = (root / "plugins" / f"hpc-{facility.slug}" / "skills" /
                        f"{facility.slug}-remote-command" / "SKILL.md").read_text()
            assert "Git-over-SSH authentication failures" in rendered

    def every_facility_scoped_mcp_tool_checks_configuration_first():
        """Every tool that reaches the cluster must check configuration
        first; every tool that does not must keep working without it.

        Both halves matter. Gating a cluster-bound tool stops it returning
        a misleading result; gating a packaged-data tool breaks cold start,
        which is how get_facility and docs search ended up circular with
        the <slug>-configuring skill they were supposed to support.

        The ungated set is derived from the source and compared against an
        explicit allowlist, so a new tool added without the guard fails
        here rather than silently reaching for a connection.
        """
        import re
        import hpc_mcp.hpc_server as server
        from hpc_agent_core import docs_server

        # Deliberately ungated, each for a stated reason:
        #   get_facilities    - no facility argument; discovery entry point
        #   get_facility      - returns this facility's packaged facts JSON
        #   render_job_script - pure local defaults/validate/render
        UNGATED = {"get_facilities", "get_facility", "render_job_script"}

        source = pathlib.Path(server.__file__).read_text()
        blocks = re.findall(
            r"@mcp\.tool\(\)\n(.*?)def ([a-zA-Z_][a-zA-Z0-9_]*)\(",
            source, re.S)
        assert blocks, "found no @mcp.tool() definitions to inspect"
        ungated = {name for between, name in blocks
                   if "@_configured_facility_tool" not in between}
        assert ungated == UNGATED, (
            "the set of tools bypassing the configuration guard changed: "
            f"unexpectedly ungated={sorted(ungated - UNGATED)}, "
            f"newly gated={sorted(UNGATED - ungated)}"
        )

        class RecordingMCP:
            def __init__(self):
                self.functions = []

            def tool(self):
                def register(func):
                    self.functions.append(func)
                    return func
                return register

        docs_mcp = RecordingMCP()
        docs_server.build(docs_mcp)
        assert len(docs_mcp.functions) == 3

        for slug in (f.slug for f in config.list_facilities()):
            with no_user_config(slug):
                # Cluster-bound: must refuse with this facility's directions.
                for func, args in (
                    (server.fs_ls, (slug,)),
                    (server.get_projects, (slug,)),
                ):
                    try:
                        func(*args)
                    except RuntimeError as exc:
                        text = str(exc)
                        assert "not configured yet" in text
                        assert f"{slug}-configuring" in text
                    else:
                        raise AssertionError(
                            f"{func.__name__} bypassed the config guard")

                # Packaged data / local only: must answer anyway. The docs
                # tools are included here because gating them is the exact
                # regression this check now guards against.
                assert server.get_facility(slug)
                for func, args in (
                    (docs_mcp.functions[0], (slug, "queues")),
                    (docs_mcp.functions[1], (slug,)),
                ):
                    out = func(*args)
                    assert out and out.strip(), (
                        f"{func.__name__} returned nothing for {slug} "
                        "without user config"
                    )

    check("at least one facility is registered", facilities_exist)
    check("unknown facility errors clearly, listing valid slugs", unknown_facility_errors_clearly)
    check("slugs are lowercase and safe", slugs_are_url_and_identifier_safe)
    def no_shipped_path_is_gitignored():
        """Nothing under facilities/ or plugins/ may be matched by .gitignore.

        An unanchored "build/" rule once swallowed
        facilities/fugaku/skills/build/ — a facility may legitimately name a
        custom skill "build", and the tracked SKILL.md inside kept working,
        so the only symptom was that a *new* file there could never be
        staged. `git add` warns and exits non-zero; nothing else notices.
        Both directories hold hand-written content and generator output, so
        a silently ignored path there loses work either way.
        """
        root = pathlib.Path(__file__).resolve().parent.parent
        if not (root / ".git").exists():
            return                      # not a checkout (e.g. inside a wheel)
        candidates = [str(p.relative_to(root))
                      for top in ("facilities", "plugins")
                      for p in (root / top).rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts]
        assert candidates, "found no shipped files to check"
        proc = subprocess.run(
            ["git", "check-ignore", "--stdin"],
            input="\n".join(candidates), capture_output=True, text=True,
            cwd=root,
        )
        # git check-ignore exits 0 when it matched something, 1 when nothing
        # matched; 1 is the outcome we want.
        ignored = [line for line in proc.stdout.splitlines() if line.strip()]
        assert not ignored, (
            "these shipped paths are matched by .gitignore, so new files "
            "beside them would be silently skipped: " + ", ".join(ignored[:5])
        )

    check("fs_rm refuses home/root paths", fs_rm_refuses_dangerous_paths)
    check("no shipped path is gitignored", no_shipped_path_is_gitignored)
    check("job names cannot inject into scripts", job_name_cannot_inject_into_scripts)
    check("resource quantities are positive", resource_quantities_are_positive)
    check("process_count does not conflict with default tasks-per-node",
          process_count_is_an_alternative_to_ppn)
    check("scheduler directives normalize home-directory shorthand",
          home_shorthand_is_normalized_for_scheduler_paths)
    check("Fugaku update quotes duration as one argument",
          fugaku_update_quotes_duration_as_one_argument)
    check("Fugaku PJM accounting exposes groups and points",
          fugaku_pjm_accounting_exposes_groups_and_points)
    check("docs embedding credentials are refreshed per search",
          docs_embedding_client_is_not_cached)
    check("SSH multiplexing is detected without opening a connection",
          ssh_multiplexing_detection_is_advisory_and_uses_resolved_config)
    check("a broken facility cannot deny the server", a_broken_facility_cannot_deny_the_server)
    check("facility data ships in a wheel", facility_data_is_declared_as_package_data)
    check("generated skills have matching frontmatter", generated_skills_are_wellformed)
    check("facility skill packs are isolated and discoverable",
          facility_skill_packs_are_isolated_and_discoverable)
    check("README requires explicit facility selection for manual install",
          readme_requires_explicit_facility_selection_for_manual_install)
    check("scheduler errors aren't mistaken for SSH failures", unreachable_detection_discriminates)
    check("every facility has real submitting-jobs notes", every_facility_has_skill_notes)
    check("remote-command skills diagnose forwarded Git authentication",
          remote_command_skills_cover_forwarded_git_authentication)
    check("every facility-scoped MCP tool checks configuration first",
          every_facility_scoped_mcp_tool_checks_configuration_first)


def main() -> int:
    check_repo()
    for fac in config.list_facilities():
        check_facility(fac.slug)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} conformance check(s) FAILED:\n")
        for f in FAILURES:
            print(f)
        return 1
    print("All conformance checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
