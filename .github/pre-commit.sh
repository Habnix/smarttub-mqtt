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

echo "📋 Running required quality gate..."
if ./scripts/quality-check.sh; then
    echo -e "${GREEN}✓ Quality gate passed${NC}"
else
    echo -e "${RED}✗ Quality gate failed${NC}"
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
