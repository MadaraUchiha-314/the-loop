Apply a session control verb (start | pause | resume | stop |
cleanup) with the full paper trail. `cleanup` is destructive: it
releases the work item's LOCAL resources — every endpoint's tmux
session, the workspace checkout (uncommitted work in it is gone) and
the machine-local session record — keeping the portable record and
touching nothing remote.
