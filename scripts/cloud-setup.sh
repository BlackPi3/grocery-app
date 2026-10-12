#!/usr/bin/env bash
# Prepares a Claude Code cloud session (claude.ai/code) to build and test this
# repo: the package in .venv, and a PostgreSQL `grocery_test` database matching
# CI, so `pytest` runs without skipping the database tests. Run by the
# SessionStart hook in .claude/settings.json, only when CLAUDE_CODE_REMOTE is
# set; on a laptop it does nothing. Best effort: it reports what failed and
# always exits 0, so a missing piece never blocks the session.

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}" || exit 0

if [ ! -x .venv/bin/grocery-app ]; then
    python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev,api]" \
        || echo "cloud-setup: installing the package failed"
fi

url=postgresql+psycopg://grocery:grocery@localhost:5432/grocery_test
as_postgres() { if [ "$(id -u)" = 0 ]; then su postgres -c "$1"; else sudo -u postgres sh -c "$1"; fi; }

if ! command -v pg_isready >/dev/null && ! ls /usr/lib/postgresql/*/bin/pg_isready >/dev/null 2>&1; then
    (apt-get update -qq && apt-get install -y -qq postgresql) >/dev/null 2>&1 \
        || echo "cloud-setup: PostgreSQL is not installed and apt could not install it"
fi
service postgresql start >/dev/null 2>&1 || pg_ctlcluster --skip-systemctl-redirect 16 main start >/dev/null 2>&1
for _ in 1 2 3 4 5 6 7 8 9 10; do pg_isready -q -h localhost 2>/dev/null && break; sleep 1; done

if pg_isready -q -h localhost 2>/dev/null; then
    as_postgres "psql -qtc \"SELECT 1 FROM pg_roles WHERE rolname='grocery'\" | grep -q 1 \
        || psql -qc \"CREATE ROLE grocery LOGIN SUPERUSER PASSWORD 'grocery'\""
    as_postgres "psql -qtc \"SELECT 1 FROM pg_database WHERE datname='grocery_test'\" | grep -q 1 \
        || createdb -O grocery grocery_test"
    [ -n "${CLAUDE_ENV_FILE:-}" ] && echo "export DATABASE_URL=$url" >> "$CLAUDE_ENV_FILE"
    echo "cloud-setup: ready. DATABASE_URL=$url (test database only)"
else
    echo "cloud-setup: PostgreSQL did not start; database tests will skip, CI still runs them"
fi
exit 0
