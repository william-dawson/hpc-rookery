Two Crux-specific caveats for notebook runs:

- **A `mode="live"` run needs the multiplexed SSH master open** (`ssh -O
  check crux` says "Master running"), exactly like any other tool call —
  the notebook can't answer a one-time-passcode prompt. Once the cache is
  complete, `mode="replay"` runs anywhere with no ALCF account.
- **Every live submission spends a real project's node-hours** (billed via
  sbank, minimum charge one node-minute per the queue floors). State which
  project the notebook bills and keep the demo-sized specs in it; a replay
  run costs nothing.
