Explain and show both halves: Grid Engine on helix/kinase with managed RTX
A4000 assignment and durable qacct, then Slurm on beta/serine with unmanaged
GPUs and ephemeral history. Present static facts, merged live resources, a docs
search, and the filesystem without changing state.

If the user wants jobs, preview them separately and ask before each allocation:
a tiny one-GPU Grid Engine job that prints `$CUDA_VISIBLE_DEVICES`, and a tiny
CPU-only Slurm job pinned to beta. Do not imply that Slurm `gpus=1` reserves its
GPU. Retrieve each scheduler's output and explain the history difference.
Raw commands use the remote-command skill's preview, permission, and recap.
