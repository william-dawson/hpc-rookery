Choose a TSUBAME resource type first. Put it in
`attributes.custom_attributes.resource_type` and use `resources.node_count` as
the number of fixed units. The resource type—not generic `gpus` or `memory`—sets
cores, memory, GPUs, and scratch. A partial spec defaults to `node_f`, priority
`-5`, and either the configured group or the free trial.

The free trial has no account and is limited to two units and three minutes.
For normal work, use a group returned by `get_projects`; never copy one from an
example. Normal jobs leave `queue_name` blank. The only evidenced explicit queue
is the subscription queue `prior`. The maximum wall time is 24 hours.

The scheduler request does not create an MPI launch line. Set `launcher`
explicitly for parallel jobs and make ranks per unit times threads per rank fit
the chosen type. With inherited environments, include `module purge` before
loading modules. Preview the generated script and ask permission before a real
submission.
