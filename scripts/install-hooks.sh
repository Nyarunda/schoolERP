#!/usr/bin/env bash
# Make git run scripts/check.sh before every push.
set -e
cd "$(dirname "$0")/.."
chmod +x .githooks/* scripts/*.sh
git config core.hooksPath .githooks
echo "pre-push hook installed. Every 'git push' now runs scripts/check.sh first."
echo "Tip: export SCHOOL_ERP_TEST_SITE=test.localhost to include the full bench tests."
