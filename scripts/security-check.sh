#!/bin/bash
# Security Check Script
# Basic security checks

set -e

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
SECRETS=$(grep -E "password|secret|key" .env.example | grep -v "changeme\|example\|your-" | grep -v "^#" || true)
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
PASSWORD_LOGS=$(grep -r -E "logger\.(info|debug|warning|error).*password" src/ --include="*.py" || true)
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
if [ -f .env.example ]; then
    echo "✅ .env.example exists"
else
    echo "❌ ERROR: .env.example is missing!"
    FAILED=1
fi

# Test 8: security documentation present
echo ""
echo "Test 8: security documentation present..."
if [ -f docs/security-review.md ]; then
    echo "✅ Security review documentation present"
else
    echo "⚠️  NOTICE: docs/security-review.md is missing"
fi

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
