#!/usr/bin/env bash
# the-loop's gate wrapper — the harness stop hook's payload (issue-109, task 34).
#
# The harness hook is a CLOCK, not a state machine. It says *when* to look; the
# graph says *what we are looking at*. So this wrapper never needs to know which
# phase the work item is in — it asks `the-loop check`, which resolves the
# current node from graph state.
#
# Claude Code: exit 2 blocks the stop and stderr goes back to the model.
# Cursor: emits {"followup_message": ...} on stdout, which Cursor auto-submits.
#
# THE_LOOP_WORK_ITEM names the work item; without it the hook is a no-op, so an
# unrelated session is never blocked by a gate that does not apply to it.
set -uo pipefail

harness="${1:-claude}"
work_item="${THE_LOOP_WORK_ITEM:-}"
attempts_file="${TMPDIR:-/tmp}/the-loop-gate-attempts-${work_item//\//_}"
max_attempts="${THE_LOOP_GATE_MAX_ATTEMPTS:-3}"

[ -z "$work_item" ] && exit 0
command -v the-loop >/dev/null 2>&1 || exit 0

output="$(the-loop check "$work_item" --format json 2>/dev/null)" || true
[ -z "$output" ] && exit 0
python3 -c "
import json,sys
d=json.loads(sys.stdin.read() or '{}')
if d.get('ok'): sys.exit(0)
cur=d.get('currentNode')
for n in d.get('nodes', []):
    if n['node']==cur and n['status'] not in ('pass','skip'):
        print(n['status']); print('\n'.join(n.get('messages') or []))
        sys.exit(1)
sys.exit(0)
" <<<"$output" > "${attempts_file}.msg" 2>/dev/null
status=$?
[ $status -eq 0 ] && { rm -f "$attempts_file" "${attempts_file}.msg"; exit 0; }

# Claude Code caps nothing, so the-loop caps it here. Cursor caps auto-followups
# natively (loop_limit, hard max 5) — the asymmetry runs the opposite way to the
# obvious guess, which is why the bound lives on this path.
attempts=$(( $(cat "$attempts_file" 2>/dev/null || echo 0) + 1 ))
echo "$attempts" > "$attempts_file"
if [ "$attempts" -gt "$max_attempts" ]; then
  rm -f "$attempts_file"
  exit 0   # bail out rather than loop forever; the CI gate is the backstop
fi

feedback="the-loop: this step is not complete.
$(tail -n +2 "${attempts_file}.msg")

Fix the above, then finish. (attempt ${attempts}/${max_attempts})"

if [ "$harness" = "cursor" ]; then
  python3 -c "
import json,sys
print(json.dumps({'followup_message': sys.stdin.read()}))
" <<<"$feedback"
  exit 0
fi
echo "$feedback" >&2
exit 2
