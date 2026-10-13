"""Miyabi (JCAHPC) registration for the unified hub.

This port is derived from the separately live-tested Miyabi-Agent repository,
and was revalidated remotely against the real machine (doctor, read-only
smoke, and a real debug-c job that ran on compute node mc001).

Miyabi asks for a one-time code at login, which a non-interactive SSH call
can never answer.  That once forced the agent to run *on* a login node with
``ssh.host=localhost``.  OpenSSH connection multiplexing lifts it: the user
opens one master connection interactively (``ssh -MNf <alias>``), entering
the code once, and every later ssh/rsync reuses it with no new prompt.
Nothing is bypassed — the code is still typed by the person, once.

``ssh.host=localhost`` remains fully supported for an agent running on a
login node.
"""
import os
from pathlib import Path

from hpc_agent_core import config
from hpc_agent_core.models import JobSpec
from facilities.miyabi.compute import PBSBackend
from facilities.registry import register_backend

SLUG = "miyabi"

FACILITY = config.register_facility(
    slug=SLUG,
    display_name="Miyabi (JCAHPC)",
    description="JCAHPC Miyabi: 1,120-node Grace Hopper GPU system plus "
                "190-node Xeon Max CPU system, PBS Professional, full-GPU "
                "and MIG queues. Reached over a multiplexed SSH connection, "
                "or locally on a login node.",
    default_host="miyabi-g",
    data_dir=Path(__file__).parent / "data",
    # No Miyabi embedding service has been verified. Keyword search is the
    # deliberate default until a real endpoint is confirmed.
    embed_base_url="",
    embed_model="",
    docs_cite_url="",
    config_example={
        "ssh": {"host": "miyabi-g"},
        "defaults": {"group": "<your-project-group>"},
    },
    setup_help=(
        "Miyabi asks for a one-time code at login, which non-interactive SSH\n"
        "cannot answer. Use OpenSSH connection multiplexing: add a host block\n"
        "to ~/.ssh/config with ControlMaster auto, ControlPath\n"
        "~/.ssh/controlmasters/%C and ControlPersist 30m (mkdir -p that\n"
        "directory, chmod 700), open the master once with `ssh -MNf <alias>`\n"
        "entering your code, then set ssh.host to that SAME alias — a bare\n"
        "hostname selects a different control socket and re-prompts.\n"
        "Running on a Miyabi login node instead? Use ssh.host=localhost.\n"
        "Set defaults.group to your own PBS project group: every job requires\n"
        "#PBS -W group_list=<group>. Never copy a group from another user.\n"
        "MIYABI_GROUP overrides the configured group.\n"
        "If a call is suddenly refused with 'Permission denied\n"
        "(keyboard-interactive)', the master connection expired — re-run\n"
        "`ssh -MNf <alias>`. Never ask the user for their one-time code."
    ),
)


def _default_group() -> str | None:
    """MIYABI_GROUP > the user's defaults.group; never a bundled fallback."""
    cfg = config.file_config(SLUG)
    return (os.environ.get(f"{FACILITY.env_prefix}_GROUP")
            or (cfg.get("defaults") or {}).get("group"))


class MiyabiBackend(PBSBackend):
    def apply_defaults(self, spec: JobSpec) -> None:
        """Resolve the mandatory per-user PBS project group.

        There is deliberately no queue default: CPU, full-GPU and MIG queues
        have materially different resources, and even their debug variants
        are not interchangeable.
        """
        if spec.attributes.account is None:
            spec.attributes.account = _default_group()
        if not spec.attributes.account:
            raise ValueError(
                "Miyabi requires a project group for every job "
                "(#PBS -W group_list=<group>). Set spec.attributes.account, "
                f"or configure defaults.group in {config.config_path(SLUG)} "
                f"(or the {FACILITY.env_prefix}_GROUP environment variable). "
                "Use your own allocation; there is no safe shared fallback."
            )


BACKEND = MiyabiBackend(facility=SLUG)
register_backend(SLUG, BACKEND)
