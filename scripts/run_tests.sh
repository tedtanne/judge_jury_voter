#!/usr/bin/env bash
# Run the unit tests and write reports to reports/ (git-ignored).
#   reports/pytest-output.txt   full pytest log
#   reports/junit.xml           machine-readable results (CI tools, IDEs)
#   reports/coverage.txt        per-module coverage, with untested lines
#   reports/summary.md          short Markdown summary (used by GitHub Actions)
# Usage:  bash scripts/run_tests.sh      (exit code is pytest's)
# The broker evaluation is separate:  python -m jjv.eval_broker --out reports/broker_eval.md
set -uo pipefail

mkdir -p reports

python -m pytest \
  -rA \
  --junitxml=reports/junit.xml \
  --cov=jjv --cov-report=term-missing \
  tests 2>&1 | tee reports/pytest-output.txt
status=${PIPESTATUS[0]}

# Coverage table only (the block pytest-cov prints).
sed -n '/coverage:/,/^TOTAL/p' reports/pytest-output.txt > reports/coverage.txt

result_line=$(grep -E '^=+ .*(passed|failed|error).* =+$' reports/pytest-output.txt | tail -1 | sed -E 's/^=+ | =+$//g')

{
  if [ "$status" -eq 0 ]; then echo "## ✅ Tests passed"; else echo "## ❌ Tests failed"; fi
  echo
  echo "**${result_line:-no result line found}** — Python $(python -c 'import platform; print(platform.python_version())')"
  echo
  echo "### Coverage by module"
  echo
  echo '```'
  cat reports/coverage.txt
  echo '```'
  echo
  echo "Modules near 0% have no unit tests yet."
} > reports/summary.md

exit "$status"
