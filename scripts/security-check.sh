#!/bin/bash
# Security checks for source, locked production dependencies and secrets.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="${PYTHON:-python}"
if [[ -x .venv/bin/python ]]; then
    PYTHON_BIN=.venv/bin/python
fi

echo "🔒 Security check for smarttub-mqtt"
echo "===================================="
echo ""

FAILED=0

# Test 1: .env in .gitignore
echo "Test 1: check .env is listed in .gitignore..."
if grep -qE "^\.env$|^\.env\b" .gitignore; then
    echo "✅ .env is listed in .gitignore"
else
    echo "❌ ERROR: .env is missing from .gitignore!"
    FAILED=1
fi

# Test 2: ensure .env is not committed to the repository
echo ""
echo "Test 2: ensure .env is not committed to the repository..."
if git ls-files | grep -q "^\.env$"; then
    echo "❌ CRITICAL: .env is committed in the repository!"
    FAILED=1
else
    echo "✅ .env is NOT in the repository"
fi

# Test 3: check .env.example for placeholder secrets
echo ""
echo "Test 3: check .env.example for placeholder secrets..."
SECRETS=$(grep -E "password|secret|key" config/.env.example | grep -v "changeme\|example\|your-" | grep -v "^#" || true)
if [ -n "$SECRETS" ]; then
    echo "❌ WARNING: Potential secrets found in .env.example:"
    echo "$SECRETS"
    FAILED=1
else
    echo "✅ No real secrets found in .env.example"
fi

# Test 4: scan for hardcoded credentials in source code
echo ""
echo "Test 4: scan for hardcoded credentials in source code..."
HARDCODED=$(grep -r -E "password\s*=\s*['\"][^'\"]+['\"]|secret\s*=\s*['\"][^'\"]+['\"]" src/ --include="*.py" | grep -v "example\|test\|changeme" || true)
if [ -n "$HARDCODED" ]; then
    echo "❌ WARNING: Potential hardcoded credentials found:"
    echo "$HARDCODED"
    FAILED=1
else
    echo "✅ No hardcoded credentials found"
fi

# Test 5: ensure passwords are not logged
echo ""
echo "Test 5: ensure passwords are not logged..."
# A status-only "***" marker is explicitly safe; any real password value is not.
PASSWORD_LOGS=$(grep -r -E "logger\.(info|debug|warning|error).*password" src/ --include="*.py" | grep -v "\*\*\*" || true)
if [ -n "$PASSWORD_LOGS" ]; then
    echo "❌ WARNING: Passwords may be logged in these locations:"
    echo "$PASSWORD_LOGS"
    FAILED=1
else
    echo "✅ No password logging patterns found"
fi

# Test 6: secure password comparisons (constant-time)
echo ""
echo "Test 6: secure password comparisons (constant-time)..."
if grep -q "secrets.compare_digest" src/web/auth.py; then
    echo "✅ secrets.compare_digest is used in auth.py"
else
    echo "❌ WARNING: secrets.compare_digest is missing in auth.py!"
    FAILED=1
fi

# Test 7: .env.example exists
echo ""
echo "Test 7: .env.example exists..."
if [ -f config/.env.example ]; then
    echo "✅ .env.example exists"
else
    echo "❌ ERROR: .env.example is missing!"
    FAILED=1
fi

# Test 8: security documentation present
echo ""
echo "Test 8: security documentation present..."
if [ -f .github/SECURITY.md ]; then
    echo "✅ Security policy present"
else
    echo "⚠️  NOTICE: .github/SECURITY.md is missing"
fi

# Tool-backed checks intentionally have no global rule exclusions. The only
# current Bandit exceptions are documented inline with their safe home-network
# binding rationale.
echo ""
echo "Test 9: Bandit static analysis..."
"$PYTHON_BIN" -m bandit -r src/ -ll -ii -f json -o bandit-report.json
echo "✅ Bandit found no medium/high findings"

echo ""
echo "Test 10: audit locked production dependencies..."
AUDIT_CACHE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/smarttub-mqtt-pip-audit.XXXXXX")"
AUDIT_REQUIREMENTS="$(mktemp "${TMPDIR:-/tmp}/smarttub-mqtt-audit-requirements.XXXXXX")"
trap 'rm -rf "$AUDIT_CACHE_DIR" "$AUDIT_REQUIREMENTS"' EXIT
# python-smarttub is locked to an immutable Git commit and intentionally has
# no PyPI record. pip-audit cannot query it, so audit every registry-published
# production dependency rather than silently weakening the complete audit.
grep -v '^python-smarttub @ git+' requirements.lock > "$AUDIT_REQUIREMENTS"
"$PYTHON_BIN" -m pip_audit --requirement "$AUDIT_REQUIREMENTS" --no-deps --strict \
    --cache-dir "$AUDIT_CACHE_DIR" --format json --output pip-audit-report.json
echo "✅ Registry-published locked production dependencies passed pip-audit"

echo ""
echo "Test 11: compare repository secrets with reviewed baseline..."
SECRET_SCAN_FILES=()
while IFS= read -r -d '' file; do
    SECRET_SCAN_FILES+=("$file")
done < <(git ls-files --cached --others --exclude-standard -z)
"$PYTHON_BIN" -m detect_secrets scan --slim \
    --exclude-files '^\.secrets\.baseline$' "${SECRET_SCAN_FILES[@]}" > .secrets.baseline.current
if ! diff --unified .secrets.baseline .secrets.baseline.current; then
    rm -f .secrets.baseline.current
    echo "❌ New potential secret detected; review and intentionally update .secrets.baseline"
    exit 1
fi
rm -f .secrets.baseline.current
echo "✅ No new potential secrets"

# Ergebnis
echo ""
echo "===================================="
if [ $FAILED -eq 0 ]; then
    echo "✅ All security checks passed!"
    exit 0
else
    echo "❌ Security checks failed!"
    echo "Please address the issues listed above."
    exit 1
fi
