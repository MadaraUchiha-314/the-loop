# Evidence — the mechanism, against a live tmux (issue-240)

Testing plan rows: **T1** (the new delivery submits, with and without a read-only client
attached) and **T11** (which tmux versions carry the guard, and why the failure itself
cannot be reproduced on this machine).

Environment: Linux 6.18.5, **tmux 3.4** (`/usr/bin/tmux`). The read-only client is a real
`tmux attach-session -r`, given a pty with
`script -q -c "…" /dev/null` and left attached throughout.

## T1a — the new delivery, with a read-only observer attached

The four commands below are exactly the ones `TmuxRunner.deliver` issues, in order, with
the same buffer names and flags.

```console
$ tmux new-session -d -s loop-readonly-probe -- sh
$ setsid script -q -c "tmux attach-session -r -t loop-readonly-probe" /dev/null &

### clients attached to the session
client=/dev/pts/1 readonly=1

### the delivery the-loop now issues, verbatim
load-buffer(prompt)  exit=0
paste-buffer -p      exit=0
load-buffer(submit)  exit=0
paste-buffer         exit=0

### what the pane actually ran
delivered-with-a-read-only-observer-attached

### buffers left behind (must be empty)
```

`readonly=1` is tmux's own `#{client_readonly}`, so the observer genuinely is the state the
ticket describes. The pane **ran the pasted command**, which is the whole claim: the prompt
arrived bracketed and the unbracketed carriage return submitted it. `tmux list-buffers`
printed nothing afterwards — both `-d` flags did their work (R3.4).

## T1b — the same delivery with no client attached (R1.5, the ordinary case)

```console
$ tmux new-session -d -s loop-noclient -- sh
### clients: none
0
delivery exit=0
delivered-with-no-client-attached
```

## T11a — this machine cannot reproduce the failure, and why

```console
$ tmux -V
tmux 3.4
$ tmux new-session -d -s loop-sk -- sh
$ setsid script -q -c "tmux attach-session -r -t loop-sk" /dev/null &
$ tmux list-clients -t loop-sk -F 'readonly=#{client_readonly}'
readonly=1
$ tmux send-keys -t loop-sk Enter
send-keys exit=0
```

A genuinely read-only client is attached and `send-keys` **succeeds** — because tmux 3.4
has no such guard. The reporter's tmux is 3.7b. So the bug is real and version-gated, and
no command run here can produce it; T11b is the evidence that stands in for it.

## T11b — which tmux versions refuse it

`cmd-send-keys.c` fetched at each release tag and at `master`, counting the guard and the
`CMD_READONLY` flag it arrived with:

```console
$ for v in 3.4 3.5a 3.6 master; do … grep -c 'client is read-only' … ; done
3.4      guard=0  CMD_READONLY=0
3.5a     guard=0  CMD_READONLY=0
3.6      guard=0  CMD_READONLY=0
master   guard=1  CMD_READONLY=1
```

The guard, in `master`'s `cmd_send_keys_exec` (`cmd-send-keys.c` rev 1.81, 2026-06-11):

```c
        if (tc != NULL && tc->flags & CLIENT_READONLY && !args_has(args, 'X')) {
                cmdq_error(item, "client is read-only");
                return (CMD_RETURN_ERROR);
        }
```

## T11c — why `-t` cannot avoid it (the ticket's suggested fix 1)

`tc` above is the **target client**, and `cmd-queue.c` resolves it from `-c` — or, with no
`-c`, from the current client. `-t` is not consulted:

```c
        if (entry->flags & CMD_CLIENT_CFLAG) {
                tc = cmd_find_client(item, args_get(args, 'c'), quiet);
                …
        } else if (entry->flags & CMD_CLIENT_TFLAG) {
                tc = cmd_find_client(item, args_get(args, 't'), quiet);
```

`send-keys` carries `CMD_CLIENT_CFLAG`, so the first branch applies. `cmd_find_client(item,
NULL, …)` → `cmd_find_current_client`, which for a command client with no session of its own
(the daemon's `tmux send-keys` subprocess) falls through to `cmd_find_best_session(NULL, …)`
→ `cmd_find_best_client(s)`: the most-recently-active client attached to that session — the
read-only observer. Caching a pane id and sending to `%N` changes `item->target`, not
`item->target_client`, so it would be refused identically.

## T11d — why `paste-buffer` is immune

```c
const struct cmd_entry cmd_paste_buffer_entry = {
        .args = { "db:prSs:t:", 0, 0, NULL },
        .target = { 't', CMD_FIND_PANE, 0 },
        .flags = CMD_AFTERHOOK,
        .exec = cmd_paste_buffer_exec
};
```

No `CMD_CLIENT_CFLAG`, no `CMD_CLIENT_TFLAG`, and `cmd_paste_buffer_exec` never reads a
client: it writes to the target pane's `wp->event` directly. The only read-only test that
applies is the one in `server-client.c`, which is about the client **issuing** the command
— the daemon's own subprocess, which was never read-only.

Nothing captured here contains a token, a credential, a hostname or personal data.
