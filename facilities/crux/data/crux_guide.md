# Crux orientation

This is a practical, hand-written guide for driving ALCF's Crux system
through this agent. It was written from ALCF's public Crux documentation
and the PBS Professional command reference, and the port it documents was
live-validated on 2026-11-02 (doctor, read-only smoke against the real
sbank/qstat/pbsnodes, and real one-node debug jobs run end to end through
the tools). Recorded limits can still drift as ALCF adjusts the machine —
refresh them with the commands below when precision matters.

## What Crux is

Crux is Argonne's compact Cray EX system: 256 liquid-cooled compute blades'
worth of nodes (64 blades, four nodes each) tied together with a Slingshot
interconnect, good for roughly a petaflop of CPU work. There are no GPUs at
all. Each node carries two AMD EPYC 7742 "Rome" processors — 128 physical
cores, or 256 hardware threads once SMT is counted — and 256 GB of DDR4
memory. The two sockets split the node into eight NUMA domains of 16 cores
apiece, which matters when you are pinning ranks or threads (see the MPI
section).

You log in on user access nodes named `crux-uan-0001` and `crux-uan-0002`
(the gateway is `crux.alcf.anl.gov`); those run different silicon (Milan)
than the compute nodes, so do not benchmark there.

## Connection model

Every ALCF login asks for a one-time passcode — from the SafeNet MobilePASS+
app or a hardware token — and a non-interactive SSH call can never answer
that prompt. The working arrangement is the same one this agent uses on
other MFA-gated machines:

1. Add an alias block to `~/.ssh/config` (substituting your ALCF username):

   ```sshconfig
   Host crux
       HostName crux.alcf.anl.gov
       User <your-ALCF-username>
       ControlMaster auto
       ControlPath ~/.ssh/controlmasters/%C
       ControlPersist 30m
   ```

2. `mkdir -p ~/.ssh/controlmasters && chmod 700 ~/.ssh/controlmasters`
3. Open the master yourself, once: `ssh -MNf crux` — this is the one step
   where you type the passcode. Check it with `ssh -O check crux`.
4. Point this facility's config (`ssh.host`) at that **same alias** — a bare
   hostname resolves to a different control socket and re-prompts.

If calls suddenly fail with a permission-denied error, the master has
expired; re-run `ssh -MNf crux`. Never ask a user for their passcode and
never try to script one. An agent already running on a Crux access node
should use `ssh.host = "localhost"` instead — no SSH at all.

## The scheduler: ALCF's PBS

Crux is scheduled by PBS Professional. Three things are mandatory on every
submission or the server refuses the job outright:

- `-A <project>` — an allocation project you belong to. Find yours with
  `sbank-list-allocations -r crux` (or the `get_projects` tool).
- `-l walltime=HH:MM:SS` — hours may exceed 24 (`72:00:00` is fine).
- `-l filesystems=...` — the filesystems the job touches, from `home` and
  `eagle`. A job only runs while every filesystem it names is up, so name
  only what you really use.

Beyond those, ALCF allocates **whole nodes**: you ask for nodes with
`-l select=<N>:system=crux` plus `-l place=scatter`, and each node arrives
with all of its cores, threads, and memory. There is no partial-node
request, so a "memory" or "exclusive" request on the spec has nothing left
to select — the node is yours entirely either way.

Output handling is fixed by the site: `-k doe` streams stdout and stderr
straight to the directory `qsub` ran in as `<jobname>.o<seq>` and
`<jobname>.e<seq>`. This backend always runs `qsub` from `~/agent/jobs/`
(where it also writes the rendered script), so a job's output lands next to
its script rather than loose in your home root.

### Queues

| queue | nodes | walltime | character |
|---|---|---|---|
| `debug` | 1–4 | 5 min – 2 h | quick tests; one running + one queued job per user, ≤8 nodes across all debug jobs |
| `workq-route` | 1–176 | 5 min – 24 h | production routing queue → `workq`; ≤100 jobs per project |
| `workq` | 1–176 | 5 min – 24 h | execution queue behind `workq-route`; 20 queued+running / 10 running per project |
| `preemptable` | 1–10 | 5 min – 72 h | can be killed at any time when demand work waits; ≤20 jobs per project |
| `demand` | 1–64 | 5 min – 1 h | only usable after ALCF grants access (email support) |

Default for this agent: `workq-route` when you don't say. Use `debug` for
short validation runs. Avoid `preemptable` for anything you cannot afford
to lose mid-run — and if you do use it, this backend automatically adds
`-r y` so a preempted job is rerun from scratch once the demand job
finishes. `demand` needs a human to have requested access first.

One trap worth knowing: PBS accepts a job into `workq-route` and *returns a
job id* before routing it. If the job then fits no execution queue (say, 10
nodes with a 30-hour walltime), it is dropped — and because `qsub` already
finished, **you never see an error and the job never appears in qstat**.
That is why this backend checks node count and walltime against the table
above offline, before submission — and why you should re-check the table
with `qstat -Qf <queue>` rather than trusting this page's copy of it.

### Reservations

On Crux a reservation *is* a queue: `pbs_rstat` lists the ones you can use
and shows each one's queue name. Pass that name as
`spec.attributes.reservation_id` (not `queue_name`) and the backend submits
into it as `#PBS -q <name>`. Reservations have no time padding at the end —
everything still running is killed the moment the reservation expires.

## MPI, OpenMP, and the 256-thread footgun

Cray MPICH is the MPI, and rank placement happens at launch time via
`mpiexec`, not in the PBS select statement — the scheduler only hands you
whole nodes. The useful `mpiexec` options:

- `-n` total ranks across the job, `--ppn` ranks per node
- `--depth` hardware threads of spacing per rank (used with `--cpu-bind`)
- `--cpu-bind` — `depth` and `core` are the usual choices; `numa`/`socket`
  for coarser pinning; `list:` pins exact cores
- `--env VAR=value` for environment settings

How spacing works: with `--cpu-bind core`, `--depth` counts **physical
cores**, so `--depth 1` binds each rank to one physical core (128 ranks
fills a node with no SMT sharing), while `--depth 2` gives each rank two
physical cores — pair it with `OMP_NUM_THREADS=2` for one thread per core.
With `--cpu-bind depth`, `--depth` counts hardware threads instead. When in
doubt, run `numactl --hardware` on a compute node and check what the binding
did before scaling up. The NUMA layout (eight domains of 16 cores) is what
`--cpu-bind numa` and friends are really slicing.

The footgun: `OMP_NUM_THREADS` starts life at **256** on compute nodes — one
per hardware thread. Any OpenMP-adjacent code that doesn't set it explicitly
will oversubscribe catastrophically. Set it every time, per rank.

For multiple independent programs on one allocation, background several
`mpiexec` calls and `wait` on them; if they should land on disjoint nodes,
split `$PBS_NODEFILE` into per-run hostfiles and pass each to `--hostfile`.

## Storage

| area | path | quota | backed up | use for |
|---|---|---|---|---|
| home | `/home` | 50 GB per user | yes (tape) | configs, small files, binaries |
| eagle | `/eagle` (`/lus/eagle/projects`) | per project directory | no | large files, heavy compute-node I/O |

Check where you stand with `myquota` (home) and `myprojectquotas`
(project directories on eagle). Home is deliberately small — do bulk I/O
from jobs into eagle. Both are Lustre; `lfs setstripe` matters for
big multi-node writes. Whatever you touch must be named in the job's
`-l filesystems` directive (the agent defaults it to `home:eagle`; override
with `custom_attributes.filesystems` if you want only one of them).

## Software

- **Compilers**: the default `PrgEnv-cray` module, or `PrgEnv-gnu`. Always
  build through the wrapper compilers `cc` / `CC` / `ftn` — they wire in the
  right MPI and architecture flags for whichever environment is loaded.
  `--craype-verbose` shows what a wrapper actually runs.
- **More software**: `module use /soft/modulefiles` exposes ALCF's extra
  tree; `module load spack-pe-base` then brings in cmake and friends.
  Query what exists with `module avail` rather than assuming.
- **Python**: a plain `python3 -m venv` plus pip is the supported pattern
  today (mpi4py is known to install fine); ALCF has announced optimized
  conda stacks but they were not there when this guide was written.
- **Containers**: not yet — Apptainer is planned but unavailable on Crux
  at port time. The backend rejects container specs rather than pretending.
- **Internet**: outbound access needs the site proxy,
  `http://proxy.alcf.anl.gov:3128` (export it as `http_proxy`, `https_proxy`,
  and `ftp_proxy`).
- **Big builds**: compile on a compute node, not the access node —
  `qsub -I -q workq -A <project> -l select=1:system=crux,walltime=HH:MM:SS`
  gets you one interactively.

## Accounting and balance

Node-hours are tracked by `sbank` per project and machine. `sbank-list-
allocations -r crux` shows what's left of yours (the agent's `get_projects`
and `get_project_allocations` tools wrap this); `sbank-list-jobs -p
<project> -r crux` shows charged jobs. Queue priority favors projects with
a positive balance, bigger jobs, and shorter runs — a stale walltime request
genuinely costs priority.

## Monitoring and diagnosis

- `get_job_status` reads the full `qstat -fx` record, including finished
  jobs (ALCF keeps about two weeks of history) and exit status.
- The **comment field is the diagnostic**. "Not running" reasons, holds,
  and deletion notices all land there; read it before wondering why
  anything is stuck.
- `qstat -xu $USER` lists your recent jobs; `qstat -was1 <jobid>` puts the
  comment on one line; `qstat -Q` lists queues.
- A job killed from the `preemptable` queue shows up deleted "at request of
  the scheduler" and — with the `-r y` this backend adds — requeues to run
  again later. That is preemption working, not a crash.
- `pbsnodes -avSj` is a node-state table (the `get_resources` tool folds it
  in); `pbsnodes -l` lists nodes that are down and why
  (`get_drained_nodes`).
- `qalter` changes a queued (or, for walltime only, running) job's name,
  walltime, project, or size; `qmove` moves a queued job between queues —
  the `update_job` tool maps onto both.

Machine status lives at status.alcf.anl.gov; people problems go to
support@alcf.anl.gov; accounts, projects, and a graphical sbank view live
in MyALCF (my.alcf.anl.gov).

## A minimal job, end to end

What this backend renders for a one-node, ten-minute, two-rank job in
`debug`, with `myproject` charged:

```bash
#!/bin/bash -l
#PBS -N agent-job
#PBS -q debug
#PBS -A myproject
#PBS -l select=1:system=crux
#PBS -l place=scatter
#PBS -l walltime=00:10:00
#PBS -l filesystems=home:eagle
#PBS -k doe

cd "$PBS_O_WORKDIR"

echo hello from $(hostname)
```

Submit with the `submit_job` tool (or preview it with `render_job_script`
first — the agent always shows you what will run). Output appears as
`agent-job.o<seq>` and `agent-job.e<seq>` in `~/agent/jobs/`, and the job's
`meta_data.workdir` points there.
