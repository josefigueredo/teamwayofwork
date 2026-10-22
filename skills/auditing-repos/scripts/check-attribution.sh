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
#        check-attribution.sh --file <draft>   scan one draft only, before posting
#
# --file is for a comment on someone else's PR: there the branch's commits,
# diff and PR bodies are the author's, not yours to judge or fix, so it never
# touches git, gh or Jira.
set -uo pipefail

# Assembled at runtime so this file does not itself read as an attribution.
# Living list — extend it when a new vendor appears. `codex` matters in
# particular: ~/.agents/skills/ exists because Codex and Copilot CLI read from
# there, so the detector must know the names of the runtimes it ships to.
VENDOR='(claude|anthropic|copilot|codex|chatgpt|gpt-[0-9]|openai|gemini|llama|mistral|grok|deepseek|qwen|llm|\bai\b)'
TRAILER="co[- ]authored[- ]by:[^\\n]*${VENDOR}"
PHRASE="(generated|created|written|authored|produced|assisted)[ -]?(with|by)[^\\n]{0,24}${VENDOR}"
BADGE='(🤖|:robot:)'
CLAIM="(this|the) (pr|commit|change|issue|report)[^\\n]{0,40}${VENDOR}[^\\n]{0,20}(wrote|generated|authored)"
PAT="${TRAILER}|${PHRASE}|${BADGE}|${CLAIM}"

fail=0
flag() { echo "✗ $1"; fail=1; }
pass() { echo "✓ $1"; }
scan() { rg -iP --no-heading -m3 "$PAT" 2>/dev/null; }

if [ "${1:-}" = "--file" ]; then
  draft="${2:-}"
  if [ -z "$draft" ] || [ ! -r "$draft" ]; then
    echo "✗ cannot read draft '$draft' — nothing was checked"
    exit 2
  fi
  echo "── attribution sweep: $draft ──"
  hit=$(scan < "$draft")
  [ -n "$hit" ] && { flag "in the draft:"; echo "$hit" | sed 's/^/    /'; } \
                || pass "$(basename "$draft") clean"
  exit "$fail"
fi

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
  # Comments live on the same endpoint for issues and PRs, but the numbers come
  # from two different lists. Iterating only PRs left every comment on a
  # standalone issue unchecked — including the correction blocks that
  # publishing.md tells you to add.
  nums=$( { gh pr list --state all --limit 20 --json number --jq '.[].number' 2>/dev/null
            gh issue list --state all --limit 40 --json number --jq '.[].number' 2>/dev/null
          } | sort -un )
  ncom=0
  for n in $nums; do
    c=$(gh api "repos/{owner}/{repo}/issues/$n/comments" --paginate \
        --jq ".[] | select(.user.login==\"$me\") | .body" 2>/dev/null)
    [ -n "$c" ] && ncom=$((ncom+1))
    hit=$(printf '%s' "$c" | scan)
    [ -n "$hit" ] && { flag "in a comment on #$n:"; echo "$hit" | sed 's/^/    /'; found=1; }
  done
  [ "$found" -eq 0 ] && pass "GitHub clean ($(echo "$nums" | grep -c . ) items, $ncom with own comments)"
else
  echo "· skipped published artifacts (no gh, or not a GitHub repo)"
fi

. "$(dirname "${BASH_SOURCE[0]}")/jira-env.sh"
# 5. Jira comments authored by this account on referenced tickets.
# Three outcomes that must never look alike: checked and clean, nothing to
# check, and could not check. The previous version printed the same ✓ for all
# three — including with a dead token, while naming the ticket it had not read.
if [ -n "${JIRA_BASE_URL:-}" ] && [ -n "${JIRA_API_TOKEN:-}" ] && [ -n "${JIRA_EMAIL:-}" ]; then
  keys=$(git log "$BASE"..HEAD --format='%B' 2>/dev/null | rg -o '[A-Z][A-Z0-9]+-[0-9]+' | sort -u)
  [ -z "$keys" ] && keys=$(gh pr list --state all --limit 30 --json title --jq '.[].title' 2>/dev/null | rg -o '[A-Z][A-Z0-9]+-[0-9]+' | sort -u)
  [ -z "$keys" ] && keys=$(git rev-parse --abbrev-ref HEAD | rg -o '[A-Z][A-Z0-9]+-[0-9]+' | sort -u)

  # The regex matches any ABC-123 shape, including references to other teams'
  # projects and the occasional false positive. When PROJECT_KEY is set, only
  # look up tickets that belong to it.
  if [ -n "${JIRA_PROJECT_KEY:-}" ] && [ -n "$keys" ]; then
    keys=$(printf '%s\n' $keys | rg "^${JIRA_PROJECT_KEY}-[0-9]+$" || true)
  fi

  if [ -z "$keys" ]; then
    echo "· no Jira keys found in commits, PR titles or branch name — nothing checked"
  else
    jcode=$(curl -s -o /dev/null -w '%{http_code}' -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
            "$JIRA_BASE_URL/rest/api/3/myself" 2>/dev/null || echo 000)
    if [ "$jcode" != "200" ]; then
      # Not a pass. Tickets are referenced and cannot be read: unverifiable is
      # a failure, not a clean bill of health.
      flag "Jira auth failed (HTTP $jcode) — cannot check $(echo $keys | tr '\n' ' ')"
      echo "    an unauthenticated Jira returns 404 for tickets that do exist"
    else
      jfound=0; jseen=0
      for k in $keys; do
        raw=$(curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
              "$JIRA_BASE_URL/rest/api/2/issue/$k/comment?maxResults=100" 2>/dev/null)
        n=$(printf '%s' "$raw" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin); print(len(d.get('comments',[])) if 'comments' in d else -1)
except Exception: print(-1)" 2>/dev/null)
        if [ "${n:--1}" -lt 0 ]; then
          flag "Jira $k unreadable — response was not a comment list"; jfound=1; continue
        fi
        jseen=$((jseen+n))
        hit=$(printf '%s' "$raw" | python3 -c "import sys,json
d=json.load(sys.stdin); print('\n'.join(c.get('body','') for c in d.get('comments',[])))" 2>/dev/null | scan)
        [ -n "$hit" ] && { flag "in Jira $k:"; echo "$hit" | sed 's/^/    /'; jfound=1; }
      done
      [ "$jfound" -eq 0 ] && pass "Jira clean ($jseen comments across $(echo $keys | tr '\n' ' '))"
    fi
  fi
else
  echo "· skipped Jira (env vars not set)"
fi

echo
# Deliberately not "ATTRIBUTION FOUND": a failure here can also mean a surface
# could not be read. Claiming the stronger finding would be the same overstatement
# this skill exists to prevent.
[ "$fail" -eq 0 ] && echo "no attribution found on any reachable surface" \
                  || echo "PROBLEMS ABOVE — attribution found, or a surface could not be checked"
exit "$fail"
