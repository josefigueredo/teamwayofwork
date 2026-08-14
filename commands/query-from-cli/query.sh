#!/usr/bin/env bash
set -euo pipefail

DEFAULT_MODEL="copilot"

usage() {
  cat <<'EOF'
Usage: q [--model=claude|codex|copilot|gemini] <prompt>

Quick AI query from terminal. Defaults to claude.
All CLIs run in lightweight mode (no MCPs, plugins, or skills).

Examples:
  q "command to rank folders by last modified recursively"
  q --model=gemini "how to find large files on macOS"
  q --model=codex "regex to match IPv6 addresses"
  q --model=copilot "git command to squash last 3 commits"
EOF
  exit 1
}

[[ $# -eq 0 ]] && usage

model="$DEFAULT_MODEL"

# Parse --model= flag
if [[ "$1" == --model=* ]]; then
  model="${1#--model=}"
  shift
fi

[[ $# -eq 0 ]] && usage

# Forces plain-text output since none of these CLIs render markdown in a terminal.
TERMINAL_PREAMBLE="Respond in plain text formatted for a terminal: "\
"no markdown (no **, #, backticks, bullet symbols); short lines; plain prose or simple numbered steps only. "\
"Tables are allowed but must be hand-aligned with spaces/pipes for a monospace terminal, not markdown table syntax. "\
"Reply in the same language as the question below. "\
"This is a one-shot query with no way to reply back: never end your answer with a clarifying question. "\
"If the question is ambiguous or missing context, pick the most likely interpretation, answer it fully, and briefly note the assumption in one line. "\
"If you truly cannot give a useful answer without more detail, still provide your best attempt for the most likely case, "\
"then add one final line: 're-run with your original prompt plus the missing detail to get a more precise answer'. "\
"Skip filler preambles like 'Sure, here is...'; go straight to the answer. "\
"Only use tools (shell, file reads, web) if the question truly requires inspecting the current environment; otherwise answer from your own knowledge. "\
"Be concise and direct."

prompt="$TERMINAL_PREAMBLE"$'\n\n'"Question: $*"

case "$model" in
  claude)
    claude -p --strict-mcp-config --disable-slash-commands "$prompt"
    ;;
  gemini)
    gemini -p "$prompt" --extensions "none" --allowed-mcp-server-names "none" 2>/dev/null
    ;;
  codex)
    codex exec --skip-git-repo-check --ephemeral --json "$prompt" 2>/dev/null \
      | jq -r 'select(.type == "item.completed") | .item.text // empty'
    ;;
  copilot)
    copilot -p "$prompt" --silent --disable-builtin-mcps --no-custom-instructions --allow-all-tools
    ;;
  *)
    echo "Unknown model: $model (choose: claude, codex, copilot, gemini)" >&2
    exit 1
    ;;
esac
