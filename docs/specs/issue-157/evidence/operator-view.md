# Evidence — T11, the command as an operator sees it (issue-157)

> The manual exploratory row of `testing-plan.md`, run against the **real** command
> on this machine (no `cursor-agent`, no `claude`), 2026-08-06. Every invocation is
> either `--dry-run` or refused, so nothing here changed the machine.

## `the-loop install --help`

```text
usage: the-loop install [-h] [--scope {user,project}]
                        [--project-dir PROJECT_DIR] [--from MARKETPLACE_REPO]
                        [--dry-run] [--format {table,json}]
                        [COMPONENT ...]

Install the-loop's CLI and its Claude Code / Cursor plugin (user or project
scope)

positional arguments:
  COMPONENT             What to install: any of cli, claude, cursor, or 'all'.
                        Default: the CLI plus every harness found on PATH.

options:
  -h, --help            show this help message and exit
  --scope {user,project}
                        Install for your user account (default) or for one
                        project only.
  --project-dir PROJECT_DIR
                        The project for --scope project (default: current
                        directory).
  --from MARKETPLACE_REPO
                        Marketplace repository as owner/repo. Default: the CLI
                        config's routing.harnessPlugins.marketplaceRepo, else
                        MadaraUchiha-314/the-loop.
  --dry-run             Print the plan and change nothing.
  --format {table,json}
                        Output format (default: table).
```

## The clone route, previewed

```text
$ the-loop install cursor --dry-run
the-loop install · component: cursor · scope: user · marketplace: MadaraUchiha-314/the-loop · dry run
Component  Outcome  Step                                                                       Command / file                                                                                               Detail                        
---------  -------  -------------------------------------------------------------------------  -----------------------------------------------------------------------------------------------------------  ------------------------------
cursor     planned  clone MadaraUchiha-314/the-loop into /root/.cursor/plugins/local/the-loop  /usr/bin/git clone -- https://github.com/MadaraUchiha-314/the-loop.git /root/.cursor/plugins/local/the-loop  cursor-agent not found on PATH
```

## An upgrade never becomes an install (R1.3)

```text
$ the-loop upgrade cursor --dry-run
the-loop upgrade · component: cursor · scope: user · marketplace: MadaraUchiha-314/the-loop · dry run
Component  Outcome  Step                                    Command / file  Detail                                                                                                      
---------  -------  --------------------------------------  --------------  ------------------------------------------------------------------------------------------------------------
cursor     skipped  upgrade the the-loop plugin for cursor  —               nothing to upgrade: no checkout at /root/.cursor/plugins/local/the-loop; run `the-loop install cursor` first
```

## A scope that cannot be expressed (R3.2)

```text
$ the-loop install cursor --scope project --dry-run
the-loop install · component: cursor · scope: project (.) · marketplace: MadaraUchiha-314/the-loop · dry run
Component  Outcome  Step                                    Command / file  Detail                                                                                                                                                                                                                         
---------  -------  --------------------------------------  --------------  -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
cursor     skipped  install the the-loop plugin for cursor  —               cursor-agent not found on PATH, and Cursor documents no project-local plugin directory, so a project-scoped install cannot be expressed; re-run with --scope user, or install it from Cursor with /add-plugin in that workspace
```

## Abuse case 1 — an invalid marketplace never reaches `git` (R7.3, security §1)

```text
$ the-loop install cursor --from "owner/repo; rm -rf /"
marketplace repository 'owner/repo; rm -rf /' is not of the form owner/repo; refusing to install a plugin from it
$ echo $?
2
```

Refused at plan time: no step exists, so nothing is executed and no URL is built.

## Nothing was created

```text
$ ls ~/.cursor 2>&1
ls: cannot access '/root/.cursor': No such file or directory
```
