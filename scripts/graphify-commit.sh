#!/usr/bin/env bash
# Commit graphify-out/ back to the branch the graph was built from (issue-385).
#
# Run by .github/workflows/graphify.yml after `graphify extract` + `cluster-only`, and
# driven directly by cli/tests/test_graphify_commit_integration.py against a bare repo.
#
#   scripts/graphify-commit.sh [branch]      (default: main)
#
# - Nothing changed under graphify-out/  -> exit 0, no commit.
# - Something changed                    -> ONE commit carrying only graphify-out/, as
#   `github-actions[bot]`, then a push that rebases onto the remote tip first. The
#   release workflow lands a `bump:` commit on main on its own schedule, so a plain push
#   can be rejected as non-fast-forward; a rebase is safe because the two commits touch
#   disjoint paths. A rebase that does conflict is aborted and reported, never forced.
# - The push is retried with backoff (GRAPHIFY_PUSH_BACKOFF seconds, doubling; default 2,
#   0 in tests) and gives up after five attempts with a non-zero exit — fail closed.
#
# Never `--force`: the branch is main.
set -euo pipefail

branch="${1:-main}"
remote="${GRAPHIFY_REMOTE:-origin}"
backoff="${GRAPHIFY_PUSH_BACKOFF:-2}"
built="${GITHUB_SHA:-$(git rev-parse HEAD)}"

# The identity the release workflow already commits under. Overridable through git's own
# environment so a test can run the script under its own name.
export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-github-actions[bot]}"
export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"
export GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-$GIT_AUTHOR_NAME}"
export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-$GIT_AUTHOR_EMAIL}"

git add -A -- graphify-out
if git diff --cached --quiet -- graphify-out; then
  echo "graphify: nothing changed under graphify-out/; no commit"
  exit 0
fi

git commit -q -m "chore(graphify): rebuild the knowledge graph for ${built:0:7}" -- graphify-out
echo "graphify: committed $(git rev-parse --short HEAD) ($(git diff --stat HEAD~1 HEAD | tail -1))"

for attempt in 1 2 3 4 5; do
  git fetch -q "$remote" "$branch"
  # --autostash: anything the build left modified outside graphify-out/ must not block
  # the rebase (it is not committed either way).
  if ! git rebase -q --autostash FETCH_HEAD; then
    git rebase --abort || true
    echo "graphify: rebase conflict against ${remote}/${branch}; not forcing — resolve by re-running the workflow" >&2
    exit 1
  fi
  if git push -q "$remote" "HEAD:refs/heads/${branch}"; then
    echo "graphify: pushed $(git rev-parse --short HEAD) to ${remote}/${branch}"
    exit 0
  fi
  wait_for=$(( backoff * (2 ** (attempt - 1)) ))
  echo "graphify: push attempt ${attempt} rejected; retrying in ${wait_for}s" >&2
  sleep "$wait_for"
done

echo "graphify: giving up after 5 push attempts" >&2
exit 1
