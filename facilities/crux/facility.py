"""Crux (Argonne Leadership Computing Facility) registration — see PORTING.md.

Crux is ALCF's 256-node HPE Cray EX CPU system (dual AMD EPYC 7742 Rome
per node), scheduled by PBS Professional with sbank node-hour accounting.
The backend lives in compute.py (a fresh SchedulerBackend subclass, because
ALCF's PBS dialect shares almost nothing with Miyabi's — see that module's
docstring). This file registers the facility and adds the one piece of
behavior that belongs to the facility rather than the scheduler dialect:

- apply_defaults: the production queue to use when the caller doesn't name
  one, and the mandatory ALCF project (``#PBS -A``) resolved from the
  *user's* config — which project to bill is a per-user choice, never a
  bundled fact.

Connection model: every ALCF login asks for a one-time passcode (SafeNet
MobilePASS+ or a hardware token), which a non-interactive SSH call can
never answer. The supported arrangement is OpenSSH connection multiplexing
(one authenticated master, every later call reuses it) or — for an agent
running on a Crux access node — ``ssh.host = "localhost"``. Nothing is
bypassed: the passcode is still typed by the person, once.

This port was live-validated on 2026-11-02 (facility.json carries
``live_validated: true``): doctor green, read-only smoke against the real
sbank/pbsnodes/qstat, and real one-node debug jobs submitted through the
tools, polled to completion, and read back.
"""
import os
from pathlib import Path

from hpc_agent_core import config
from hpc_agent_core.models import JobSpec
from facilities.crux.compute import CruxPBSBackend
from facilities.registry import register_backend

SLUG = "crux"

FACILITY = config.register_facility(
    slug=SLUG,
    display_name="Crux (ALCF)",
    description="Argonne's ALCF Crux: 256-node HPE Cray EX AMD Rome CPU "
                 "cluster, PBS Professional with sbank accounting; every "
                 "job needs a project (-A) and filesystems directive, and "
                 "login uses a one-time passcode over a multiplexed SSH "
                 "connection.",
    default_host="crux",
    data_dir=Path(__file__).parent / "data",
    # No ALCF embedding endpoint has been verified. Keyword (BM25) search is
    # the deliberate default until a real endpoint exists — same choice
    # Miyabi made, and it avoids the stale-embeddings drift the R-CCS Cloud
    # review flagged.
    embed_base_url="",
    embed_model="",
    # ALCF's user guides are a stable, public, version-controlled site
    # (github.com/argonne-lcf/user-guides); PORTING.md §3's "genuinely
    # stable and worth pointing at" case.
    docs_cite_url="https://docs.alcf.anl.gov/crux/",
    config_example={
        "ssh": {"host": "crux"},
        "defaults": {"account": "<your-ALCF-project>"},
    },
    setup_help=(
        "ALCF login asks for a one-time passcode from MobilePASS+ or a\n"
        "hardware token, which non-interactive SSH cannot answer. Use\n"
        "OpenSSH connection multiplexing: add a 'crux' block to\n"
        "~/.ssh/config with HostName crux.alcf.anl.gov, your User, and\n"
        "ControlMaster auto, ControlPath ~/.ssh/controlmasters/%C,\n"
        "ControlPersist 30m (mkdir -p that directory, chmod 700), open the\n"
        "master once with `ssh -MNf crux` entering your passcode, then set\n"
        "ssh.host to that SAME alias — a bare hostname selects a different\n"
        "control socket and re-prompts.\n"
        "Running on a Crux access node instead? Use ssh.host=localhost.\n"
        "Set defaults.account to one of your ALCF projects (see\n"
        "sbank-list-allocations -r crux): every job needs #PBS -A. Never\n"
        "copy a project from another user. CRUX_ACCOUNT overrides the\n"
        "configured default."
    ),
)


def _default_account() -> str | None:
    """CRUX_ACCOUNT > the user's defaults.account; never a bundled fallback
    — which project to bill is the user's own choice."""
    cfg = config.file_config(SLUG)
    return (os.environ.get(f"{FACILITY.env_prefix}_ACCOUNT")
            or (cfg.get("defaults") or {}).get("account"))


class CruxBackend(CruxPBSBackend):
    """The scheduler dialect plus this facility's user-level defaults."""

    def apply_defaults(self, spec: JobSpec) -> None:
        """Fill the production queue and the user's default project.

        Queue: `workq-route` (the production routing queue) when the caller
        names neither a queue nor a reservation — `debug` is deliberately
        NOT the default because its per-user limits (one running job) make
        it a poor automatic choice; callers doing quick tests should name
        it explicitly. A reservation_id suppresses the queue default: the
        reservation itself is the destination.
        """
        if (not spec.attributes.queue_name
                and not spec.attributes.reservation_id):
            spec.attributes.queue_name = (
                config.load_facts(SLUG).get("defaults", {}).get(
                    "queue", "workq-route")
            )
        if spec.attributes.account is None:
            spec.attributes.account = _default_account()
        if not spec.attributes.account:
            raise ValueError(
                "No project named. Every Crux job is billed to an ALCF "
                "project (#PBS -A is mandatory — qsub refuses the job "
                "without one). Set spec.attributes.account to a project you "
                f"belong to, or configure defaults.account in "
                f"{config.config_path(SLUG)} (or the "
                f"{FACILITY.env_prefix}_ACCOUNT environment variable). Use "
                "get_projects to see your active projects; there is no safe "
                "shared fallback."
            )


BACKEND = CruxBackend(facility=SLUG)
register_backend(SLUG, BACKEND)
