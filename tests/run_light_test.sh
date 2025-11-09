#!/bin/bash
# SmartTub Light Mode Test Runner
# Convenience script to run light mode tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         SmartTub Light Mode Discovery Test                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if config exists
if [ ! -f "config/smarttub.yaml" ]; then
    echo -e "${RED}❌ Error: config/smarttub.yaml not found${NC}"
    echo "Please create config from example first"
    exit 1
fi

# Load config (simple extraction)
EMAIL=$(grep "email:" config/smarttub.yaml | awk '{print $2}' | tr -d '"')
PASSWORD=$(grep "password:" config/smarttub.yaml | awk '{print $2}' | tr -d '"')
DEVICE_ID=$(grep "device_id:" config/smarttub.yaml | awk '{print $2}' | tr -d '"')

if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
    echo -e "${RED}❌ Error: Could not read credentials from config${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Configuration loaded${NC}"
echo -e "   Device: ${DEVICE_ID:-auto-detect}"
echo ""

# Menu
echo "Select test mode:"
echo ""
echo "  ${YELLOW}1)${NC} Quick Test (8 modes, ~45s) - RECOMMENDED"
echo "  ${YELLOW}2)${NC} Color Modes Only (9 modes, ~60s)"
echo "  ${YELLOW}3)${NC} Dynamic Modes Only (7 modes, ~50s)"
echo "  ${YELLOW}4)${NC} Full Test (18 modes, ~120s)"
echo "  ${YELLOW}5)${NC} Custom modes"
echo "  ${YELLOW}6)${NC} Zone 2 Quick Test"
echo ""
read -p "Choice [1-6]: " choice

ZONE=1
ARGS=""

case $choice in
    1)
        echo -e "${GREEN}Running Quick Test (Zone 1)...${NC}"
        ARGS="--quick --zone 1"
        ;;
    2)
        echo -e "${GREEN}Running Color Modes Test...${NC}"
        ARGS="--colors --zone 1"
        ;;
    3)
        echo -e "${GREEN}Running Dynamic Modes Test...${NC}"
        ARGS="--dynamic --zone 1"
        ;;
    4)
        echo -e "${YELLOW}⚠️  Full test will take ~2 minutes${NC}"
        read -p "Continue? [y/N]: " confirm
        if [[ ! $confirm =~ ^[Yy]$ ]]; then
            echo "Cancelled"
            exit 0
        fi
        echo -e "${GREEN}Running Full Test...${NC}"
        ARGS="--full --zone 1"
        ;;
    5)
        echo "Enter modes (comma-separated, e.g., PURPLE,ORANGE,RED):"
        read -p "> " modes
        echo -e "${GREEN}Running Custom Test...${NC}"
        ARGS="--modes $modes --zone 1"
        ;;
    6)
        echo -e "${GREEN}Running Quick Test (Zone 2)...${NC}"
        ARGS="--quick --zone 2"
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

# Optional: adjust timing
echo ""
echo "Default timing: 3s wait, 2s delay between tests"
read -p "Adjust timing? [y/N]: " adjust_timing

if [[ $adjust_timing =~ ^[Yy]$ ]]; then
    read -p "Wait time after mode change (seconds) [3.0]: " wait_time
    read -p "Delay between tests (seconds) [2.0]: " delay_time
    
    if [ -n "$wait_time" ]; then
        ARGS="$ARGS --wait $wait_time"
    fi
    if [ -n "$delay_time" ]; then
        ARGS="$ARGS --delay $delay_time"
    fi
fi

echo ""
echo -e "${BLUE}Starting test...${NC}"
echo ""

# Run test
python3 tests/test_light_modes.py \
    --email "$EMAIL" \
    --password "$PASSWORD" \
    ${DEVICE_ID:+--device-id "$DEVICE_ID"} \
    $ARGS

echo ""
echo -e "${GREEN}✅ Test completed!${NC}"
echo ""
echo "Results saved to tests/light_mode_test_zone*.json"
echo ""
echo "Next steps:"
echo "  1. Review the summary above"
echo "  2. Check the JSON file for detailed results"
echo "  3. Update openhab/transform/smarttub_lightmode.map with working modes"
echo ""
