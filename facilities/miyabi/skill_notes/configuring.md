   - **The recommended setup is a multiplexed SSH alias.** Miyabi asks for a
     one-time code at login, which a non-interactive SSH call can never
     answer — so the user authenticates once, interactively, and every later
     `ssh`/`rsync` reuses that connection.

     Have the user add a block to `~/.ssh/config` (substituting their
     account):

     ```
     Host miyabi-g
         HostName miyabi-g.jcahpc.jp
         User <account>
         ControlMaster auto
         ControlPath ~/.ssh/controlmasters/%C
         ControlPersist 30m
     ```

     then, after `mkdir -p ~/.ssh/controlmasters && chmod 700
     ~/.ssh/controlmasters`, open the master once:

     ```bash
     ssh -MNf miyabi-g       # they enter their one-time code here
     ssh -O check miyabi-g   # Master running (pid=…)
     ```

     Set `"host"` to that **same alias**. A bare hostname, or a different
     user or port, selects a different control socket and re-prompts.
   - **Running on a Miyabi login node instead?** Use `"host": "localhost"`,
     which is direct local execution and involves no SSH at all.

**Never ask the user for their one-time code, and never try to script or
automate entering one.** The whole arrangement depends on the code being
typed by the person, once, in their own terminal.

**Also set `defaults.group`** — every PBS job needs the user's own project
group (`#PBS -W group_list=<group>`), and `submit_job` refuses without one.
`MIYABI_GROUP` overrides the file. Never reuse a group from an example or
from another user; `id -Gn` on the login node shows theirs.
