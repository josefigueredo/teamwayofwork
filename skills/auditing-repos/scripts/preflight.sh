#!/usr/bin/env bash
# Preflight for a repo audit. Reports what is available and what is missing.
# Never exits non-zero for a missing optional tool — the audit adapts instead.
set -uo pipefail

ok=0; warn=0; miss=0
say() { printf '%-26s %s\n' "$1" "$2"; }
have() { command -v "$1" >/dev/null 2>&1; }

echo "── repository ──"
if git rev-parse --git-dir >/dev/null 2>&1; then
  if ! git rev-parse --verify --quiet HEAD >/dev/null 2>&1; then
    # A cloned-but-empty repository. Nothing to audit yet, and every diff-based
    # check below would compare against nothing and report clean.
    say "git repo" "yes, but NO COMMITS YET"
    say "  →" "there is nothing to audit until something is committed"
    miss=$((miss+1))
  else
    say "git repo" "yes ($(git rev-parse --abbrev-ref HEAD))"
    say "working tree" "$([ -z "$(git status --porcelain)" ] && echo clean || echo "DIRTY — commit or stash before auditing")"
    say "default branch" "$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|origin/||' || echo unknown)"
    ok=$((ok+1))
  fi
else
  say "git repo" "NO — this skill audits a git repository"; miss=$((miss+1))
fi

echo
echo "── github ──"
if have gh && gh auth status >/dev/null 2>&1; then
  perm=$(gh repo view --json viewerPermission --jq '.viewerPermission' 2>/dev/null || echo "?")
  say "gh auth" "yes"
  say "repo permission" "$perm"
  case "$perm" in
    ADMIN|MAINTAIN|WRITE) ;;
    *) say "  ⚠" "no write access — you can report but not publish"; warn=$((warn+1));;
  esac
  say "issues enabled" "$(gh repo view --json hasIssuesEnabled --jq '.hasIssuesEnabled' 2>/dev/null || echo '?')"
else
  say "gh auth" "NO — findings can only be written locally"; warn=$((warn+1))
fi

echo
echo "── jira (optional) ──"
missing_jira=()
for v in IC_JIRA_BASE_URL IC_JIRA_USER_EMAIL IC_JIRA_API_TOKEN IC_JIRA_PROJECT_KEY; do
  [ -z "${!v:-}" ] && missing_jira+=("$v")
done
if [ ${#missing_jira[@]} -eq 0 ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' -u "$IC_JIRA_USER_EMAIL:$IC_JIRA_API_TOKEN" \
         "$IC_JIRA_BASE_URL/rest/api/3/myself" 2>/dev/null || echo 000)
  if [ "$code" = "200" ]; then
    say "jira auth" "yes (project $IC_JIRA_PROJECT_KEY)"
  else
    say "jira auth" "HTTP $code — token expired or revoked, NOT a permissions problem"
    say "  note" "an unauthenticated Jira returns 404 for real tickets. Never conclude"
    say "  " "'the ticket does not exist' from a 404 while /myself returns 401."
    warn=$((warn+1))
  fi
else
  say "jira" "skipped (missing: ${missing_jira[*]})"
fi

echo
echo "── audit report safety ──"
if git rev-parse --git-dir >/dev/null 2>&1; then
  if git check-ignore -q AUDIT-REPORT.md 2>/dev/null; then
    say "AUDIT-REPORT.md" "ignored — safe to write in the repo root"
  else
    say "AUDIT-REPORT.md" "NOT IGNORED in this repo"
    say "  →" "the report holds detailed security findings and is a draft until"
    say "  " "approved. A git add -A would publish it to history before the gate."
    say "  fix" "echo 'AUDIT-REPORT.md' >> .gitignore   (or write to the scratchpad)"
    warn=$((warn+1))
  fi
fi

echo
echo "── verification tooling ──"
for t in docker uv rg fd; do
  have "$t" && say "$t" "yes" || { say "$t" "no — some claims cannot be verified by running them"; warn=$((warn+1)); }
done

echo
echo "ok=$ok warnings=$warn blocking=$miss"
[ "$miss" -gt 0 ] && exit 1 || exit 0
