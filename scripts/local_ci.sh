#!/usr/bin/env bash
# The whole CI (.github/workflows/ci.yml) on this machine's bench, for when GitHub Actions cannot run.
#
#   cd <a checkout of this repository, at the commit to test>
#   bash scripts/local_ci.sh              # every step; a summary at the end; exit 1 if any step failed
#   bash scripts/local_ci.sh --quick      # quick checks and the three test suites only (no site builds)
#   bash scripts/local_ci.sh --report     # also record the result on GitHub as the commit status "local-ci"
#
# It tests the checkout it is run from: the bench's School ERP folder is moved to that commit (detached), and the
# Control Center app must be this checkout's (apps/stemic_control is a link to <checkout>/platform/stemic_control).
# Needs the CI sites on the bench: test.localhost (School ERP), admin.localhost (Control Center) and
# books.localhost (Control Center with ERPNext). The end-to-end and restore steps run as the database account in
# /etc/stemic/secrets.env when that file exists, as production does.
set -uo pipefail

BENCH=${BENCH:-$HOME/frappe-bench}
QUICK=0 REPORT=0
for arg in "$@"; do
    case "$arg" in
        --quick) QUICK=1 ;;
        --report) REPORT=1 ;;
        *) echo "unknown option $arg" >&2; exit 2 ;;
    esac
done

REPO=$(git rev-parse --show-toplevel) || exit 2
COMMIT=$(git -C "$REPO" rev-parse HEAD)
SHORT=${COMMIT:0:7}
LOG="$BENCH/logs/local-ci-$SHORT.log"
: > "$LOG"
declare -a RESULTS=()
FAILED=0

step() {  # step "<name>" <command...>: run it, log it, record PASS/FAIL (failures do not stop the run)
    local name=$1 start=$SECONDS
    shift
    local out
    out=$(mktemp)
    printf '\n== %s\n' "$name" | tee -a "$LOG"
    "$@" >"$out" 2>&1
    local code=$?
    cat "$out" >>"$LOG"
    # bench run-tests can exit 0 with failures reported in its output: read the step's own output too
    if [ "$code" = 0 ] && ! grep -qE "^(FAILED|FAIL:)" "$out"; then
        RESULTS+=("PASS  $name ($((SECONDS - start))s)")
    else
        RESULTS+=("FAIL  $name ($((SECONDS - start))s)")
        FAILED=1
        grep -E "✖|FAIL:|ERROR:|Error: |AssertionError|line [0-9]+, in test_" "$out" | tail -n 8 | sed 's/^/      /'
    fi
    rm -f "$out"
    echo "${RESULTS[-1]}"
}

# ----------------------------------------------------------------------------- the bench runs this commit
if [ "$(readlink -f "$BENCH/apps/stemic_control")" != "$(readlink -f "$REPO/platform/stemic_control")" ]; then
    echo "$BENCH/apps/stemic_control is not this checkout's Control Center ($REPO/platform/stemic_control)." >&2
    exit 2
fi
dirty=$(git -C "$REPO" status --porcelain)
if [ -n "$dirty" ]; then
    echo "note: uncommitted changes in $REPO are tested by the Control Center steps but not by School ERP's"
    [ "$REPORT" = 1 ] && { echo "--report needs a clean checkout: commit first" >&2; exit 2; }
fi
SCHOOL="$BENCH/apps/school_erp"
if [ "$(readlink -f "$SCHOOL")" != "$(readlink -f "$REPO")" ]; then
    if [ -n "$(git -C "$SCHOOL" status --porcelain)" ]; then
        echo "$SCHOOL has uncommitted changes; commit or stash them first." >&2
        exit 2
    fi
    git -C "$SCHOOL" fetch -q "$REPO" "$COMMIT" && git -C "$SCHOOL" switch -q --detach "$COMMIT" || exit 2
fi
echo "testing $SHORT ($(git -C "$REPO" log -1 --format=%s | cut -c1-70)); log: $LOG"
export PATH="$BENCH/env/bin:$PATH"
cd "$BENCH" || exit 2
for site in test.localhost admin.localhost books.localhost; do
    [ -d "sites/$site" ] && bench --site "$site" migrate >>"$LOG" 2>&1 || echo "note: could not migrate $site (see the log)"
done

# ----------------------------------------------------------------------------- the CI's steps
step "Quick checks" bash -c "cd '$REPO' && bash scripts/check.sh"
step "Control plane checks (no bench)" bash -c "cd '$REPO' && python -m compileall -q platform/stemic_control/stemic_control \
    && PYTHONPATH=platform/stemic_control python -m pytest -q -p no:cacheprovider \
       platform/stemic_control/stemic_control/tests/test_billing_integrity_contract.py \
       platform/stemic_control/stemic_control/tests/test_tax_rules.py \
       platform/stemic_control/stemic_control/tests/test_etims_integration_contract.py"
step "School ERP tests (test.localhost)" bench --site test.localhost run-tests --app school_erp
step "Control Center tests (admin.localhost)" bench --site admin.localhost run-tests --app stemic_control
if [ -d sites/books.localhost ]; then
    step "Stemic's books (books.localhost, with ERPNext)" bench --site books.localhost run-tests --module stemic_control.tests.test_accounting
else
    RESULTS+=("SKIP  Stemic's books: no books.localhost (bench new-site books.localhost --install-app erpnext --install-app stemic_control)")
fi

if [ "$QUICK" = 0 ]; then
    cd "$BENCH/sites" || exit 2
    step "Billing concurrency (snapshot isolation off, with the control race)" \
        env STEMIC_RACE_SNAPSHOT_ISOLATION=OFF ../env/bin/python ../apps/stemic_control/scripts/billing_concurrency.py admin.localhost protected control
    step "Billing concurrency (server default)" ../env/bin/python ../apps/stemic_control/scripts/billing_concurrency.py admin.localhost protected
    if [ -r /etc/stemic/secrets.env ]; then
        set -a; . /etc/stemic/secrets.env; set +a  # as production: the limited database account
    fi
    step "End-to-end onboarding (real site build)" ../env/bin/python ../apps/stemic_control/scripts/e2e_onboarding.py admin.localhost
    step "Backup restores (test.localhost)" ../env/bin/python ../apps/stemic_control/scripts/restore_check.py admin.localhost test.localhost
fi

# ----------------------------------------------------------------------------- summary
printf '\n==== local CI for %s\n' "$SHORT"
printf '%s\n' "${RESULTS[@]}"
if [ "$REPORT" = 1 ]; then
    state=$([ "$FAILED" = 0 ] && echo success || echo failure)
    passed=$(printf '%s\n' "${RESULTS[@]}" | grep -c "^PASS")
    gh api -X POST "repos/{owner}/{repo}/statuses/$COMMIT" -f state="$state" -f context="local-ci" \
        -f description="$passed of ${#RESULTS[@]} steps passed on $(hostname) ($([ "$QUICK" = 1 ] && echo quick || echo full))" >/dev/null \
        && echo "recorded on GitHub as local-ci: $state" || echo "could not record the status on GitHub"
fi
exit "$FAILED"
