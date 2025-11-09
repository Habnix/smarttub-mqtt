#!/bin/bash
# Quick test runner for both zones

# Get credentials from running container
EMAIL=$(docker exec smarttub-mqtt printenv SMARTTUB_EMAIL)
PASSWORD=$(docker exec smarttub-mqtt printenv SMARTTUB_PASSWORD)

export SMARTTUB_EMAIL="$EMAIL"
export SMARTTUB_PASSWORD="$PASSWORD"

echo "🚀 Starting Light Mode Tests for Both Zones"
echo "=============================================="
echo "Email: $EMAIL"
echo ""

# Zone 1 Quick Test
echo "📍 Testing Zone 1 (Quick - 8 modes)..."
SMARTTUB_EMAIL="$EMAIL" SMARTTUB_PASSWORD="$PASSWORD" python3 tests/test_light_modes.py \
  --quick \
  --zone 1 \
  --wait 4.0 \
  --verify 5 \
  --delay 2.5 \
  --output zone1_quick_$(date +%Y%m%d_%H%M%S).json

echo ""
echo "✅ Zone 1 completed!"
echo ""
echo "⏳ Waiting 10 seconds before Zone 2..."
sleep 10
echo ""

# Zone 2 Quick Test
echo "📍 Testing Zone 2 (Quick - 8 modes)..."
SMARTTUB_EMAIL="$EMAIL" SMARTTUB_PASSWORD="$PASSWORD" python3 tests/test_light_modes.py \
  --quick \
  --zone 2 \
  --wait 4.0 \
  --verify 5 \
  --delay 2.5 \
  --output zone2_quick_$(date +%Y%m%d_%H%M%S).json

echo ""
echo "✅ Zone 2 completed!"
echo ""
echo "🎉 All tests completed!"
echo ""
echo "Results saved in tests/results/"
