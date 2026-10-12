#!/usr/bin/env bash
# Pre-push sweep. Catches the mechanical mistakes that are cheaper to grep for
# than to discover in CI. Run before every push during an audit.
#
# Usage: sweep.sh [base-ref]     (default: origin/HEAD, else main)
set -uo pipefail

BASE="${1:-}"
if [ -z "$BASE" ]; then
  BASE=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
  [ -z "$BASE" ] && for c in main master; do
    git rev-parse --verify --quiet "$c" >/dev/null && { BASE="$c"; break; }
  done
fi

# A base that does not resolve makes every diff-based check below return
# nothing, and "nothing" reads as "clean". A check that passes silently when
# it could not run is worse than no check at all.
if ! git rev-parse --verify --quiet HEAD >/dev/null 2>&1; then
  echo "✗ repository has no commits — nothing to sweep"
  exit 2
fi
if ! git rev-parse --verify --quiet "$BASE" >/dev/null 2>&1; then
  echo "✗ base ref '${BASE:-<none found>}' does not resolve — cannot diff, refusing to report clean"
  branches=$(git branch --format='%(refname:short)' | tr '\n' ' ')
  echo "  available: ${branches:-<none>}"
  echo "  pass one explicitly: sweep.sh <base-ref>"
  exit 2
fi

fail=0
flag() { echo "✗ $1"; fail=1; }
pass() { echo "✓ $1"; }

echo "── sweeping $(git rev-parse --abbrev-ref HEAD) against $BASE ──"

# 1. 40-character identifiers.
# TruffleHog's Lob detector matches ANY 40-char alphanumeric token and reports
# it as a *verified* secret, failing CI. Test function names hit this.
hits=$(rg -o '\b[A-Za-z0-9_]{40}\b' --glob '!*.lock' --glob '!*.md' --glob '!*.sum' . 2>/dev/null | head -5)
[ -n "$hits" ] && { flag "40-char identifiers (TruffleHog Lob false positive):"; echo "$hits" | sed 's/^/    /'; } \
                || pass "no 40-char identifiers"

# 2. Local agent/editor tooling that a 'git add -A' sweeps up.
staged_junk=$(git diff --name-only "$BASE"...HEAD 2>/dev/null \
  | rg '^\.(serena|idea|vscode|cursor|aider|claude/settings\.local)' || true)
[ -n "$staged_junk" ] && { flag "local tooling in the diff:"; echo "$staged_junk" | sed 's/^/    /'; } \
                       || pass "no local tooling files"

# 3. LLM attribution — commits only here; the dedicated sweep covers every
# surface (diff, branch name, PRs, issues, comments, Jira). The rule is
# absolute: see references/no-attribution.md.
if [ -x "$(dirname "$0")/check-attribution.sh" ]; then
  if "$(dirname "$0")/check-attribution.sh" "$BASE" >/tmp/.attr.$$ 2>&1; then
    pass "no LLM attribution (commits, diff, branch, GitHub, Jira)"
  else
    # Not "attribution found": the sub-check also fails when a surface could
    # not be read. Naming the stronger conclusion here would undo the fix made
    # inside check-attribution.sh for exactly this reason.
    flag "attribution check did not pass:"; rg '^✗' /tmp/.attr.$$ | sed 's/^/    /'
  fi
  rm -f /tmp/.attr.$$
fi

# 4. Every pinned action SHA exists AND matches the version in its comment.
# Existence alone is not enough: a real SHA sitting next to "# v0.36.0" that
# actually belongs to v0.32.0 is a comment that lies, which is worse than no
# comment — the next reader trusts it and skips the check.
if command -v gh >/dev/null 2>&1; then
  bad=0; checked=0
  while IFS= read -r line; do
    ref="${line%%|*}"; tag="${line##*|}"
    repo="${ref%%@*}"; sha="${ref##*@}"
    case "$repo" in */*/*) repo="$(echo "$repo" | cut -d/ -f1,2)";; esac
    [ ${#sha} -eq 40 ] || continue
    checked=$((checked+1))

    if ! gh api "repos/$repo/commits/$sha" --jq '.sha' >/dev/null 2>&1; then
      flag "action SHA does not exist: $repo@$sha"; bad=1; continue
    fi

    # No version comment to check against.
    [ "$tag" = "$line" ] || [ -z "$tag" ] && continue

    obj=$(gh api "repos/$repo/git/ref/tags/$tag" --jq '.object.sha + " " + .object.type' 2>/dev/null) || {
      flag "$repo: comment says $tag, but that tag does not exist"; bad=1; continue; }
    tsha="${obj%% *}"; ttype="${obj##* }"
    [ "$ttype" = "tag" ] && tsha=$(gh api "repos/$repo/git/tags/$tsha" --jq '.object.sha' 2>/dev/null)
    [ "$tsha" = "$sha" ] || { flag "$repo@$sha is NOT $tag (that tag is $tsha)"; bad=1; }
  done < <(rg -oIP 'uses:\s*\K[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+@[a-f0-9]{40}(?:\s*#\s*(v[0-9][^\s]*))?' .github/workflows 2>/dev/null \
           | sed -E 's/[[:space:]]*#[[:space:]]*(v[^[:space:]]+)$/|\1/' | sort -u)
  if [ "$checked" -eq 0 ]; then
    echo "· no pinned action SHAs to verify"
  elif [ "$bad" -eq 0 ]; then
    pass "all $checked pinned action SHAs exist and match their version comment"
  fi
else
  echo "· skipped action SHA check (no gh)"
fi

# 5. Mutable action refs — the thing an audit usually flags in others.
mutable=$(rg -oIP 'uses:\s*\K[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+@(main|master|v[0-9.]+)$' .github/workflows 2>/dev/null | sort -u || true)
[ -n "$mutable" ] && { echo "· mutable action refs (intentional?):"; echo "$mutable" | sed 's/^/    /'; } \
                  || pass "no mutable action refs"

echo
[ "$fail" -eq 0 ] && echo "sweep clean" || echo "sweep found problems — fix before pushing"
exit "$fail"
