   - **The recommended setup is a multiplexed SSH alias.** ALCF asks for a
     one-time passcode (MobilePASS+ app or hardware token) at every login,
     which a non-interactive SSH call can never answer — so the user
     authenticates once, interactively, and every later `ssh`/`rsync` reuses
     that connection.

     Have the user add a block to `~/.ssh/config` (substituting their ALCF
     username):

     ```
     Host crux
         HostName crux.alcf.anl.gov
         User <their-ALCF-username>
         ControlMaster auto
         ControlPath ~/.ssh/controlmasters/%C
         ControlPersist 30m
     ```

     then, after `mkdir -p ~/.ssh/controlmasters && chmod 700
     ~/.ssh/controlmasters`, open the master once:

     ```bash
     ssh -MNf crux        # they type their one-time passcode here
     ssh -O check crux    # Master running (pid=…)
     ```

     Set `"host"` to that **same alias**. A bare hostname, or a different
     user or port, selects a different control socket and re-prompts.
   - **Running on a Crux access node instead?** Use `"host": "localhost"`
     (direct local execution, no SSH at all).

**Never ask the user for their one-time passcode, and never try to script or
automate entering one.** The whole arrangement depends on the passcode being
typed by the person, once, in their own terminal.

**Also set `defaults.account`** — every job is billed to an ALCF project
(`#PBS -A` is mandatory), and `submit_job` refuses without one. Find the
user's projects with `get_projects(facility="{{SLUG}}")` once the connection
works, or ask them to run `sbank-list-allocations -r crux`. `{{ENV_PREFIX}}_ACCOUNT`
overrides the file. Never reuse a project from an example or from another
user.
