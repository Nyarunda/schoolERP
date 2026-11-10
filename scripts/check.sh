#!/usr/bin/env bash
# Quick checks before every push. Fast (seconds) and needs no bench.
# Add the full Frappe test-suite by setting SCHOOL_ERP_TEST_SITE, e.g.
#   SCHOOL_ERP_TEST_SITE=test.localhost ./scripts/check.sh
set -euo pipefail
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
step() { echo -e "\n${GREEN}==> $*${NC}"; }
fail() { echo -e "${RED}FAILED: $*${NC}"; exit 1; }

# Prefer the bench's python if we're inside a bench (apps/school_erp)
PY=python3
[ -x ../../env/bin/python ] && PY=../../env/bin/python

step "Python compiles"
$PY -m compileall -q school_erp tools scripts || fail "syntax error"

step "DocType / JSON validation"
$PY scripts/validate_app.py || fail "app validation"

step "JavaScript syntax"
if command -v node >/dev/null; then
	find school_erp -name "*.js" -not -path "*/node_modules/*" -print0 | xargs -0 -n1 node --check || fail "JS syntax"
else
	echo "node not found, skipping"
fi

step "Unit tests (business logic)"
$PY -c "import pytest" 2>/dev/null || $PY -m pip install -q pytest
$PY -c "import cryptography" 2>/dev/null || $PY -m pip install -q cryptography
$PY -m pytest -q \
  school_erp/tests/test_logic.py \
  school_erp/tests/test_document_verification_policy.py \
  school_erp/tests/test_verified_document_integrity.py \
  school_erp/tests/test_admissions.py \
  school_erp/tests/test_cbc.py \
  school_erp/tests/test_nemis.py || fail "unit tests"

step "No private keys staged"
if git rev-parse --git-dir >/dev/null 2>&1; then
	if git diff --cached --name-only | grep -Ei '\.key$|vendor_private' ; then fail "private key staged"; fi
fi

if [ -n "${SCHOOL_ERP_TEST_SITE:-}" ]; then
	BENCH_DIR="${BENCH_DIR:-$(cd ../.. && pwd)}"
	step "Frappe integration tests on site $SCHOOL_ERP_TEST_SITE (bench: $BENCH_DIR)"
	(cd "$BENCH_DIR" && bench --site "$SCHOOL_ERP_TEST_SITE" run-tests --app school_erp) || fail "integration tests"
fi

echo -e "\n${GREEN}All checks passed.${NC}"
