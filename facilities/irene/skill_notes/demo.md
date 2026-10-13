Lead with Irene's defining fact: normal jobs are CPU/MPI work on `rome`, and
the public scheduler interface is Bridge rather than raw Slurm. Show static
partitions, live `ccc_mpinfo` occupancy, the user's project associations, a
documentation search, and a home-directory listing. Keep this overview
read-only.

If the user requests a test job, preview a one-task, five-minute `rome` spec
using a project returned by `get_projects` and the configured filesystem list,
then ask before submission. Poll no faster than TGCC policy allows and inspect
`irene_<job-id>.o` after completion. Raw commands follow the remote-command
skill's preview, permission, and recap workflow.
