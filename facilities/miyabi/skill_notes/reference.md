The bundled guide is based on live inspection and smoke jobs dated
2026-07-13, but this unified port could not be revalidated because Miyabi was
unavailable. Say so when a dated fact matters.

Refresh queue limits with `qstat --rsc -x`/`qstat --limit`, modules with
`module -t avail`, storage with `show_quota`, and compute tokens with
`show_token`. Those live commands require the remote-command permission
workflow. Miyabi-G uses the `LNG` module hierarchy; Miyabi-C uses `MC`.
