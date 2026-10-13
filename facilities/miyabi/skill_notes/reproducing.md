The first live recording needs a working connection: either a multiplexed
SSH master that is currently open (`ssh -O check <alias>` says "Master
running") or an agent on a Miyabi login node with `ssh.host=localhost`. A
`mode="live"` run cannot answer a one-time-code prompt, so re-open the master
with `ssh -MNf <alias>` first if it has expired. Once the cache is complete,
`mode="replay"` can replay
the notebook elsewhere without a Miyabi account or local execution. State in
the notebook that the hub port was derived from the live-tested 2026-07-13
Miyabi-Agent implementation and should be revalidated when access returns.
