#!/bin/bash
# Pre-commit checks for SmartTub-MQTT
# Run this before committing to ensure code quality

set -e

echo "🔍 Running pre-commit checks..."
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track failures
FAILED=0

# Ruff linting
echo "📋 Running Ruff linter..."
if ruff check . --quiet; then
    echo -e "${GREEN}✓ Ruff linting passed${NC}"
else
    echo -e "${RED}✗ Ruff linting failed${NC}"
    FAILED=1
fi
echo ""

# Ruff formatting
echo "🎨 Checking code formatting..."
if ruff format --check . --quiet; then
    echo -e "${GREEN}✓ Code formatting is correct${NC}"
else
    echo -e "${YELLOW}⚠ Code formatting issues found${NC}"
    echo "Run: ruff format . to fix"
    FAILED=1
fi
echo ""

# MyPy type checking
echo "🔎 Running MyPy type checker..."
if mypy src/ --ignore-missing-imports --no-error-summary 2>/dev/null; then
    echo -e "${GREEN}✓ Type checking passed${NC}"
else
    echo -e "${YELLOW}⚠ Type checking found issues (non-blocking)${NC}"
fi
echo ""

# Pytest
echo "🧪 Running tests..."
if pytest --quiet --tb=short; then
    echo -e "${GREEN}✓ All tests passed${NC}"
else
    echo -e "${RED}✗ Tests failed${NC}"
    FAILED=1
fi
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed! Ready to commit.${NC}"
    exit 0
else
    echo -e "${RED}✗ Some checks failed. Please fix issues before committing.${NC}"
    exit 1
fi
