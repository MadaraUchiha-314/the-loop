# Security review — issue-318

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 3: below
> `security.review.humanSignOffMinTier: 4`, so no named human sign-off is required; the
> owner's PR approval is the gate.

## Threat model recap

The change adds a second *source* for the process environment — a dotenv file the CLI
config names — and keeps the boundary the-loop already enforces: the config names
variables, the environment holds values, and nothing the-loop writes carries a value. The
file is parsed by a fixed grammar (`the_loop.envfile.parse`), never evaluated or
expanded; only names absent from the environment are set; every failure is a warning
naming a path, a line number or an error class. No authorization, routing or spawn path
is touched, so the change grants nothing and widens nothing.

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | A loaded value reaching a log line, the state tree or the event log | Warnings carry the path, line numbers and error classes; names only at `debug`; the loader writes nothing to disk and emits no event | `test_envfile.py::test_a_warning_never_carries_a_value_or_a_line` (asserts the token and the malformed line's text are absent from every record at `DEBUG`) |
| A2 | A secrets file readable by other local users | `stat` mode checked on POSIX; one warning naming the mode; still loaded (a refusal would push operators back to `export`, which is as visible) | `test_envfile.py::test_a_file_readable_by_others_is_warned_about_and_still_loaded` |
| A3 | A hostile or malformed line (`$(rm -rf /)`, a name with spaces, an unterminated quote) | The grammar rejects it; the line is skipped and reported by **number**; nothing is evaluated, expanded or passed to a shell | `test_envfile.py::test_malformed_lines_are_skipped_by_number_and_the_rest_loaded`, `::test_the_grammar_reports_invalid_lines_by_number`, `::test_the_grammar_does_not_interpolate` |
| A4 | A config edit redirecting a deliberately exported credential to a file | Only names absent from the environment are set; the environment wins | `test_envfile.py::test_the_environment_wins_over_the_file`; `test_envfile_integration.py::test_an_exported_token_survives_the_env_file` |
| A5 | A path outside the config's directory (absolute, `..`) | Honoured — the operator chose it — and the **resolved** path is in every warning, so a surprising file is visible in the logs | `test_envfile.py::test_an_absolute_or_parent_path_is_honoured_and_named` |

## Checklist

- [x] AuthN/AuthZ unchanged: nothing here decides who may do what; `routing.authorizedUsers`, the control keywords and every gate are untouched.
- [x] No shell, no subprocess, no `eval`: the parser is `str.partition` and a regex over each line; the loader is `stat`, `read_text` and a dict write.
- [x] Secrets: values enter `os.environ` only; never a log line (A1), never a file, never an event; the schema `description` and every doc say the config names a path, never a value; the template and this repo's config ship the key unset.
- [x] Fail closed: a missing, unreadable or malformed file loads nothing or only its valid lines (`test_a_missing_file_warns_and_loads_nothing`, `test_a_directory_is_not_a_regular_file`, `test_an_unreadable_file_warns_with_the_error_class`); a stale or broken config loads nothing (`test_a_stale_or_broken_config_loads_nothing_and_does_not_raise`); every credential-dependent feature keeps its 13.2.0 refusal when its variable is absent.
- [x] Least privilege: the environment wins (A4); the file is read once at start and never on config reload, so a reload cannot change a running process's credentials.
- [x] Inheritance: the daemons and the service are spawned with no `env=` (unchanged) and load the file again themselves (`test_the_daemon_entry_loads_the_env_file_before_running`, `test_the_service_loads_the_env_file_before_its_config`).
- [x] Evidence redaction: every token in the tests and the evidence is a fixture string.

## Outcome

**Pass** on the autonomous checklist. No human sign-off required at tier 3; the pull
request's review is the human gate.
