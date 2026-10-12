#!/usr/bin/env bash
# Tests check 4 of sweep.sh (pinned action SHAs) offline: a throwaway repo plus
# a fake `gh` on PATH, so nothing touches the network or a real repository.
#
# With no pinned SHAs there is nothing to verify, and the sweep must say so
# instead of printing "all 0 pinned action SHAs exist" — a pass that checked
# nothing reads as a pass.
set -uo pipefail

SWEEP="$(cd "$(dirname "$0")" && pwd)/sweep.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/bin" "$tmp/repo/.github/workflows"
# Fake gh: every lookup succeeds and returns the same SHA, whatever is asked.
cat > "$tmp/bin/gh" <<'GH'
#!/usr/bin/env bash
echo "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
GH
chmod +x "$tmp/bin/gh"

cd "$tmp/repo" || exit 1
git init -q -b main
git config user.email t@example.test
git config user.name t
git commit -q --allow-empty -m "chore: init"

run_sweep() { PATH="$tmp/bin:$PATH" bash "$SWEEP" main < /dev/null 2>&1; }

pass=0; fail=0
check() { # check <description> <condition-exit-code>
  if [ "$2" -eq 0 ]; then echo "  ✓ $1"; pass=$((pass+1)); else echo "  ✗ $1"; fail=$((fail+1)); fi
}

echo "── no pinned SHAs ──"
printf 'jobs:\n  x:\n    steps:\n      - uses: actions/checkout@v4\n' > .github/workflows/ci.yml
out=$(run_sweep)
! printf '%s\n' "$out" | rg -q 'all [0-9]+ pinned action SHAs'; check "does not claim 'all N pinned action SHAs' with none" $?
printf '%s\n' "$out" | rg -q 'no pinned action SHAs to verify'; check "says there were no pinned action SHAs to verify" $?

echo "── one pinned SHA ──"
printf 'jobs:\n  x:\n    steps:\n      - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n' > .github/workflows/ci.yml
out=$(run_sweep)
printf '%s\n' "$out" | rg -q 'all 1 pinned action SHAs exist'; check "still reports 'all 1 pinned action SHAs exist'" $?

echo
echo "passed=$pass failed=$fail"
exit $(( fail > 0 ))
