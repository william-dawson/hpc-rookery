"""Offline regression test for the generated reproducible-notebook path.

Exercises the synchronous facade a notebook uses against a real MCP stdio
server, verifies lazy/replay caching, and covers the two argument-construction
bugs that previously made every generated notebook fail before doing useful
work. No SSH, scheduler, network, or Jupyter installation is required.
"""
import asyncio
import os
import tempfile
from pathlib import Path

from hpc_agent_core.client import HpcClient, connect_sync, dev_params, pinned_params


class _Result:
    is_error = False
    structured_content = {"result": {"verified": True}}
    content = []


class _RecordingSession:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return _Result()


def check_pinned_root_project() -> None:
    params = pinned_params(
        "https://github.com/william-dawson/hpc-rookery.git",
        "hpc-mcp",
        ref="main",
    )
    source = params.args[params.args.index("--from") + 1]
    assert source.endswith("@main"), source
    assert "#subdirectory=" not in source, source

    legacy = pinned_params("https://example.invalid/old.git", "old-mcp",
                           subdirectory="server")
    legacy_source = legacy.args[legacy.args.index("--from") + 1]
    assert legacy_source.endswith("#subdirectory=server"), legacy_source


def check_download_wire_name() -> None:
    async def run():
        session = _RecordingSession()
        client = HpcClient(session, mode="live")
        result = await client.fs_download(
            facility="rikyu", remote_path="results/out.json",
            local_path="downloads/out.json",
        )
        assert result == {"verified": True}
        assert session.calls == [(
            "fs_download",
            {
                "remote_path": "results/out.json",
                "local_path": "downloads/out.json",
                "facility": "rikyu",
            },
        )], session.calls

    asyncio.run(run())


def check_sync_live_lazy_replay() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "cache"
        params = dev_params("hpc_mcp", "hpc_server", env=dict(os.environ))

        with connect_sync(params, mode="lazy", cache_dir=cache) as hpc:
            facilities = hpc.get_facilities()
            assert any(f["slug"] == "rikyu" for f in facilities)
            facts = hpc.get_facility(facility="rikyu")
            assert facts["machine"] == "RIKYU"

        # Same calls must replay from the notebook cache. A server process is
        # still opened for MCP framing, but neither call reaches SSH or other
        # external state.
        with connect_sync(params, mode="replay", cache_dir=cache) as hpc:
            assert hpc.get_facilities() == facilities
            assert hpc.get_facility(facility="rikyu") == facts


def main() -> None:
    check_pinned_root_project()
    check_download_wire_name()
    check_sync_live_lazy_replay()
    print("Notebook client checks passed.")


if __name__ == "__main__":
    main()
