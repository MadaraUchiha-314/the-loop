#!/usr/bin/env sh
# the-loop SessionStart hook (Claude Code).
#
# Two jobs, in order:
#   1. Auto-upgrade the installed plugin so every new session runs the latest
#      the-loop — issue #38. The plugin is a git checkout of this repo (installed
#      via the marketplace); we fast-forward it to origin. Updated files take
#      effect for the next session (and for anything Claude Code loads after this
#      hook), so a session is "always up to date" without the user running
#      `/plugin update` by hand.
#   2. Surface the project's the-loop config so the harness loads its operating
#      rules — the original v0 reminder.
#
# Hard rules: never block a session and never fail it. The upgrade is best-effort,
# fully quiet, time-boxed, and exits 0 no matter what (offline, detached HEAD,
# no network, git missing — all fine). Cursor has no SessionStart event, so its
# equivalent reminder ships as rules/the-loop.mdc; Cursor resolves the plugin
# from the repo directly and has no hook to self-upgrade from.
#
# Opt out of the auto-upgrade with THE_LOOP_AUTO_UPGRADE=0. Tune the network
# time-box with THE_LOOP_UPGRADE_TIMEOUT (seconds, default 15).

set -u

# --- 1. Auto-upgrade the installed plugin ---------------------------------
auto_upgrade() {
	[ "${THE_LOOP_AUTO_UPGRADE:-1}" = "0" ] && return 0

	root="${CLAUDE_PLUGIN_ROOT:-}"
	[ -n "$root" ] || return 0
	command -v git >/dev/null 2>&1 || return 0
	git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0

	# Don't touch a checkout someone is actively working on (e.g. a developer
	# hacking on the-loop itself, or a local dev install). Uncommitted changes
	# would block a fast-forward anyway.
	[ -z "$(git -C "$root" status --porcelain 2>/dev/null)" ] || return 0

	# Need a named branch to fast-forward; skip a detached/pinned checkout.
	branch="$(git -C "$root" symbolic-ref --quiet --short HEAD 2>/dev/null)" || return 0
	[ -n "$branch" ] || return 0

	before="$(git -C "$root" rev-parse HEAD 2>/dev/null)" || return 0

	if command -v timeout >/dev/null 2>&1; then
		timeout "${THE_LOOP_UPGRADE_TIMEOUT:-15}" \
			git -C "$root" pull --ff-only --quiet origin "$branch" >/dev/null 2>&1 || return 0
	else
		git -C "$root" pull --ff-only --quiet origin "$branch" >/dev/null 2>&1 || return 0
	fi

	after="$(git -C "$root" rev-parse HEAD 2>/dev/null)" || return 0
	if [ -n "$after" ] && [ "$before" != "$after" ]; then
		short="$(git -C "$root" rev-parse --short HEAD 2>/dev/null)"
		echo "the-loop: auto-upgraded plugin to latest ($branch @ $short). Changes apply to your next session."
	fi
}

auto_upgrade

# --- 2. the-loop config reminder ------------------------------------------
if [ -f .the-loop/config.yaml ]; then
	echo "the-loop is initialized in this repo. Operating rules: plan→execute→self/critic-review→escalate. See .the-loop/config.yaml and the the-loop skill."
fi

exit 0
