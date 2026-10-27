**Billing warning for Step 6.** ROQUO bills GPU time to a project, so tell
the user what the test job will cost them in wall time before submitting,
and let them decline. Use the smallest useful shape: one GPU, five
minutes.

Suggested spec:

```json
{
  "name": "roquo-demo",
  "executable": "nvidia-smi",
  "arguments": ["-L"],
  "resources": {"gpus": 1},
  "attributes": {
    "queue_name": "roquo",
    "account": "<project>",
    "duration": 300
  }
}
```

`nvidia-smi -L` is a good demo payload here: it proves the aarch64 compute
node, the GPU allocation, and the `qtr` node plan all worked, in one line
of output.

**`attributes.account` is not optional in practice.** ROQUO accepts a job
without it and charges a restrictive default account, which also becomes
the owning group of any file the job writes — so the demo should resolve a
real project in Step 1 (`get_projects`) and pass it. If the user belongs
to several, ask which to charge rather than picking one. If Step 1's
`get_projects` fails, that is the SSH check failing; follow the template's
instruction and switch to `{{SLUG}}-configuring`.

**A note for Step 2.** `get_resources` shows two partitions, `roquo` and
`work`, and they are different architectures (aarch64 vs x86_64) rather
than two sizes of the same thing. Worth saying out loud when presenting
the table, because it's the single most consequential fact about this
machine.

**A note for Step 7.** The script writes to the submission directory by
default. If the job had written to `$SLURM_SCRATCH`, the output would be
gone the moment it finished — mention that when showing where output
lives, since it's the most common way people lose results here.
