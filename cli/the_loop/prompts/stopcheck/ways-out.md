Do one of these now:
  1. Continue the work in this turn.
  2. Ask a person: `the-loop ask --work-item {ref} --question "<question>"`, then end the turn.
  3. If you wait on something that is not a person (CI, another session), declare it: `the-loop wait --work-item {ref} --for "<what>" --until 30m`, then end the turn. The wait covers this one stop.
A harness that reports no background work to the-loop needs option 3 to wait on background work too.
