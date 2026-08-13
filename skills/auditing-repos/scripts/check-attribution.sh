#!/usr/bin/env bash
# Attribution sweep. The rule is absolute (see references/no-attribution.md):
# nothing produced may indicate that an LLM produced it — commits, diffs, PRs,
# issues, comments, or Jira.
#
# This file necessarily contains the patterns it detects. That is tooling, not
# a published artifact. Never plant a real attribution string in a commit to
# test it.
#
# Usage: check-attribution.sh [base-ref]
set -uo pipefail

BASE="${1:-}"
if [ -z "$BASE" ]; then
  BASE=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
  [ -z "$BASE" ] && for c in main master; do
    git rev-parse --verify --quiet "$c" >/dev/null && { BASE="$c"; break; }
  done
fi
if ! git rev-parse --verify --quiet "$BASE" >/dev/null 2>&1; then
  echo "✗ base ref '$BASE' does not resolve — refusing to report clean"
  exit 2
fi

# Assembled at runtime so this file does not itself read as an attribution.
VENDOR='(claude|anthropic|copilot|chatgpt|gpt-[0-9]|openai|gemini|llm|\bai\b)'
TRAILER="co[- ]authored[- ]by:[^\\n]*${VENDOR}"
PHRASE="(generated|created|written|authored|produced|assisted)[ -]?(with|by)[^\\n]{0,24}${VENDOR}"
BADGE='(🤖|:robot:)'
CLAIM="(this|the) (pr|commit|change|issue|report)[^\\n]{0,40}${VENDOR}[^\\n]{0,20}(wrote|generated|authored)"
PAT="${TRAILER}|${PHRASE}|${BADGE}|${CLAIM}"

fail=0
flag() { echo "✗ $1"; fail=1; }
pass() { echo "✓ $1"; }
scan() { rg -iP --no-heading -m3 "$PAT" 2>/dev/null; }

echo "── attribution sweep: $(git rev-parse --abbrev-ref HEAD) vs $BASE ──"

# 1. Commit metadata: author, committer, message, trailers.
meta=$(git log "$BASE"..HEAD --format='%an <%ae>%n%cn <%ce>%n%B' 2>/dev/null | scan)
[ -n "$meta" ] && { flag "in commit metadata:"; echo "$meta" | sed 's/^/    /'; } \
               || pass "commits clean (author, committer, body, trailers)"

# 2. Added lines in the diff: code comments, docs, workflows, the report.
added=$(git diff "$BASE"...HEAD 2>/dev/null | rg '^\+' | scan)
[ -n "$added" ] && { flag "in added lines:"; echo "$added" | sed 's/^/    /'; } \
                || pass "diff contents clean"

# 3. Branch name.
echo "$(git rev-parse --abbrev-ref HEAD)" | scan >/dev/null \
  && flag "in the branch name" || pass "branch name clean"

# 4. Published artifacts: PRs, issues and their comments.
if command -v gh >/dev/null 2>&1 && gh repo view >/dev/null 2>&1; then
  found=0
  pr=$(gh pr list --state all --limit 30 --json number,title,body --jq '.[] | "\(.number) \(.title) \(.body)"' 2>/dev/null | scan)
  [ -n "$pr" ] && { flag "in pull requests:"; echo "$pr" | sed 's/^/    /'; found=1; }

  is=$(gh issue list --state all --limit 60 --json number,title,body --jq '.[] | "\(.number) \(.title) \(.body)"' 2>/dev/null | scan)
  [ -n "$is" ] && { flag "in issues:"; echo "$is" | sed 's/^/    /'; found=1; }

  me=$(gh api user --jq '.login' 2>/dev/null)
  for n in $(gh pr list --state all --limit 15 --json number --jq '.[].number' 2>/dev/null); do
    c=$(gh api "repos/{owner}/{repo}/issues/$n/comments" \
        --jq ".[] | select(.user.login==\"$me\") | .body" 2>/dev/null | scan)
    [ -n "$c" ] && { flag "in a comment on #$n:"; echo "$c" | sed 's/^/    /'; found=1; }
  done
  [ "$found" -eq 0 ] && pass "published PRs, issues and comments clean"
else
  echo "· skipped published artifacts (no gh, or not a GitHub repo)"
fi

# 5. Jira comments authored by this account on referenced tickets.
if [ -n "${IC_JIRA_BASE_URL:-}" ] && [ -n "${IC_JIRA_API_TOKEN:-}" ] && [ -n "${IC_JIRA_USER_EMAIL:-}" ]; then
  keys=$(git log "$BASE"..HEAD --format='%B' 2>/dev/null | rg -o '[A-Z][A-Z0-9]+-[0-9]+' | sort -u)
  [ -z "$keys" ] && keys=$(gh pr list --state all --limit 30 --json title --jq '.[].title' 2>/dev/null | rg -o '[A-Z][A-Z0-9]+-[0-9]+' | sort -u)
  jfound=0
  for k in $keys; do
    body=$(curl -s -u "$IC_JIRA_USER_EMAIL:$IC_JIRA_API_TOKEN" \
      "$IC_JIRA_BASE_URL/rest/api/2/issue/$k/comment?maxResults=50" 2>/dev/null \
      | python3 -c "import sys,json;d=json.load(sys.stdin);print('\n'.join(c.get('body','') for c in d.get('comments',[])))" 2>/dev/null)
    hit=$(printf '%s' "$body" | scan)
    [ -n "$hit" ] && { flag "in Jira $k:"; echo "$hit" | sed 's/^/    /'; jfound=1; }
  done
  [ "$jfound" -eq 0 ] && pass "Jira comments clean${keys:+ ($(echo $keys | tr '\n' ' '))}"
else
  echo "· skipped Jira (env vars not set)"
fi

echo
[ "$fail" -eq 0 ] && echo "no attribution found" || echo "ATTRIBUTION FOUND — remove before publishing"
exit "$fail"
