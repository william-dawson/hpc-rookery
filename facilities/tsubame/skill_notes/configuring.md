TSUBAME4 requires non-interactive, registered SSH-key access. Register the
user's public key in the TSUBAME portal, then configure an SSH alias named
`tsubame` for `login.t4.gsic.titech.ac.jp`, or put the issued user@host in
`ssh.host`. Use `localhost` when the agent already runs on a login node.

Set `defaults.group` only to a group returned by
`get_projects(facility="{{SLUG}}")`; `TSUBAME_GROUP` overrides it. An omitted
group is meaningful and selects the strictly limited free trial. Docs search is
BM25-only because no embedding endpoint has been verified.
