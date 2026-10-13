Octopus requires non-interactive key-based SSH to the management node. Use an
SSH alias or user@host issued for the user's own account; do not invent a
public hostname. If the agent runs on an Octopus front end, use
`"host": "localhost"`.

An account override is optional because Slurm supplies each user's
`DefaultAccount`. Only configure `defaults.account` after `get_projects` has
shown that user's real associations. Docs embeddings use the shared RIKEN
endpoint when a key is available and otherwise fall back to BM25.
