#!/usr/bin/env bash
# Sourced by preflight.sh and check-attribution.sh. Resolves the Jira credentials
# into the generic names the skill documents: JIRA_BASE_URL, JIRA_EMAIL,
# JIRA_API_TOKEN and the optional JIRA_PROJECT_KEY.
#
# The IC_JIRA_* names (IC_JIRA_USER_EMAIL for the email) are a compatibility
# alias for people who already had them exported. They are read, never
# advertised, and they win over the generic ones — the same order jkan uses in
# jira-team-kit, so one shell configuration behaves the same in both tools.
jira_pick() { # jira_pick <alias> <generic>  → first non-empty value
  local a="${!1:-}" g="${!2:-}"
  printf '%s' "${a:-$g}"
}
JIRA_BASE_URL=$(jira_pick IC_JIRA_BASE_URL JIRA_BASE_URL)
JIRA_EMAIL=$(jira_pick IC_JIRA_USER_EMAIL JIRA_EMAIL)
JIRA_API_TOKEN=$(jira_pick IC_JIRA_API_TOKEN JIRA_API_TOKEN)
JIRA_PROJECT_KEY=$(jira_pick IC_JIRA_PROJECT_KEY JIRA_PROJECT_KEY)
