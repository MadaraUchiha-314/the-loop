The ingress daemons (poller, gh-webhook): whether each is running, its
pid, pidfile and logfile, and — for the poller — when it started and last
completed a cycle. Liveness is the pidfile's lock, never the heartbeat.
