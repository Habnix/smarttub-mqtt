#!/bin/bash
# Manual Test Script for Background Discovery v0.3.0
# Tests all features of the Background Discovery system
#
# Usage: ./test_background_discovery_v0.3.0.sh
#
# Prerequisites:
# - Docker and docker-compose installed
# - smarttub-mqtt container running
# - Valid SmartTub credentials in config/.env
# - MQTT broker accessible

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CONTAINER_NAME="smarttub-mqtt"
WEB_URL="http://localhost:8080"
MQTT_BROKER="${MQTT_BROKER:-localhost}"
MQTT_PORT="${MQTT_PORT:-1883}"
MQTT_BASE_TOPIC="${MQTT_BASE_TOPIC:-smarttub-mqtt}"

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Helper functions
print_header() {
    echo -e "\n${BLUE}============================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================${NC}\n"
}

print_test() {
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    echo -e "${YELLOW}[TEST $TESTS_TOTAL]${NC} $1"
}

print_success() {
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check if docker is installed
    if ! command -v docker &> /dev/null; then
        print_error "Docker not found. Please install Docker."
        exit 1
    fi
    print_success "Docker installed"
    
    # Check if docker-compose is installed
    if ! command -v docker-compose &> /dev/null; then
        print_error "docker-compose not found. Please install docker-compose."
        exit 1
    fi
    print_success "docker-compose installed"
    
    # Check if curl is installed
    if ! command -v curl &> /dev/null; then
        print_error "curl not found. Please install curl."
        exit 1
    fi
    print_success "curl installed"
    
    # Check if mosquitto_pub is installed (optional)
    if command -v mosquitto_pub &> /dev/null; then
        print_success "mosquitto_pub installed (MQTT tests enabled)"
        MQTT_TESTS_ENABLED=true
    else
        print_info "mosquitto_pub not found (MQTT command tests will be skipped)"
        MQTT_TESTS_ENABLED=false
    fi
    
    # Check if jq is installed (optional but recommended)
    if command -v jq &> /dev/null; then
        print_success "jq installed (JSON parsing enabled)"
        JQ_ENABLED=true
    else
        print_info "jq not found (install for better JSON output)"
        JQ_ENABLED=false
    fi
}

check_container() {
    print_header "Checking Container Status"
    
    print_test "Container running?"
    if docker ps | grep -q "$CONTAINER_NAME"; then
        print_success "Container '$CONTAINER_NAME' is running"
    else
        print_error "Container '$CONTAINER_NAME' is not running"
        print_info "Start with: docker-compose up -d"
        exit 1
    fi
    
    print_test "Container healthy?"
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "no-healthcheck")
    if [ "$HEALTH" = "healthy" ] || [ "$HEALTH" = "no-healthcheck" ]; then
        print_success "Container health: $HEALTH"
    else
        print_error "Container health: $HEALTH"
    fi
    
    print_test "WebUI accessible?"
    if curl -f -s "$WEB_URL/health" > /dev/null 2>&1; then
        print_success "WebUI accessible at $WEB_URL"
    else
        print_error "WebUI not accessible at $WEB_URL"
        print_info "Check container logs: docker logs $CONTAINER_NAME"
        exit 1
    fi
}

test_webui_endpoints() {
    print_header "Testing WebUI Endpoints"
    
    # Test 1: Discovery page exists
    print_test "GET /discovery (discovery page)"
    if curl -f -s "$WEB_URL/discovery" > /dev/null 2>&1; then
        print_success "Discovery page accessible"
    else
        print_error "Discovery page not accessible"
    fi
    
    # Test 2: Get status endpoint
    print_test "GET /api/discovery/status"
    RESPONSE=$(curl -s "$WEB_URL/api/discovery/status")
    if [ $? -eq 0 ]; then
        print_success "Status endpoint responds"
        if [ "$JQ_ENABLED" = true ]; then
            echo "$RESPONSE" | jq '.'
        else
            echo "$RESPONSE"
        fi
    else
        print_error "Status endpoint failed"
    fi
    
    # Test 3: Get results endpoint
    print_test "GET /api/discovery/results"
    RESPONSE=$(curl -s "$WEB_URL/api/discovery/results")
    if [ $? -eq 0 ]; then
        print_success "Results endpoint responds"
        if [ "$JQ_ENABLED" = true ]; then
            echo "$RESPONSE" | jq '.'
        else
            echo "$RESPONSE"
        fi
    else
        print_error "Results endpoint failed"
    fi
}

test_discovery_yaml_mode() {
    print_header "Testing YAML-Only Discovery Mode"
    
    print_test "Start YAML-only discovery"
    RESPONSE=$(curl -s -X POST "$WEB_URL/api/discovery/start" \
        -H "Content-Type: application/json" \
        -d '{"mode":"yaml_only"}')
    
    if echo "$RESPONSE" | grep -q "started\|completed"; then
        print_success "YAML-only discovery started"
        if [ "$JQ_ENABLED" = true ]; then
            echo "$RESPONSE" | jq '.'
        fi
    else
        print_error "YAML-only discovery failed to start"
        echo "$RESPONSE"
    fi
    
    # Wait a bit
    sleep 2
    
    print_test "Check status after YAML-only"
    RESPONSE=$(curl -s "$WEB_URL/api/discovery/status")
    STATUS=$(echo "$RESPONSE" | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
    print_info "Status: $STATUS"
    
    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "idle" ]; then
        print_success "YAML-only completed (expected: instant)"
    else
        print_error "YAML-only still running (should be instant)"
    fi
}

test_discovery_quick_mode() {
    print_header "Testing Quick Discovery Mode"
    
    print_info "This test takes ~5 minutes. Press Ctrl+C to skip."
    read -t 5 -p "Continue? [Y/n] " -n 1 -r || REPLY="Y"
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]] && [[ ! -z $REPLY ]]; then
        print_info "Skipping Quick Discovery test"
        return
    fi
    
    print_test "Start quick discovery"
    RESPONSE=$(curl -s -X POST "$WEB_URL/api/discovery/start" \
        -H "Content-Type: application/json" \
        -d '{"mode":"quick"}')
    
    if echo "$RESPONSE" | grep -q "started"; then
        print_success "Quick discovery started"
        START_TIME=$(date +%s)
    else
        print_error "Quick discovery failed to start"
        echo "$RESPONSE"
        return
    fi
    
    # Monitor progress
    print_info "Monitoring progress (updates every 10s)..."
    while true; do
        sleep 10
        RESPONSE=$(curl -s "$WEB_URL/api/discovery/status")
        STATUS=$(echo "$RESPONSE" | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
        
        if [ "$JQ_ENABLED" = true ]; then
            PROGRESS=$(echo "$RESPONSE" | jq -r '.progress.percentage // "N/A"')
            CURRENT_SPA=$(echo "$RESPONSE" | jq -r '.progress.current_spa // "N/A"')
            CURRENT_LIGHT=$(echo "$RESPONSE" | jq -r '.progress.current_light // "N/A"')
            print_info "Status: $STATUS | Progress: $PROGRESS% | Spa: $CURRENT_SPA | Light: $CURRENT_LIGHT"
        else
            print_info "Status: $STATUS"
        fi
        
        if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] || [ "$STATUS" = "idle" ]; then
            break
        fi
        
        ELAPSED=$(($(date +%s) - START_TIME))
        if [ $ELAPSED -gt 400 ]; then
            print_error "Discovery timeout (>400s for quick mode)"
            break
        fi
    done
    
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    
    if [ "$STATUS" = "completed" ]; then
        print_success "Quick discovery completed in ${DURATION}s"
    else
        print_error "Quick discovery ended with status: $STATUS"
    fi
    
    # Check results
    print_test "Verify results saved"
    RESULTS=$(curl -s "$WEB_URL/api/discovery/results")
    if echo "$RESULTS" | grep -q "detected_modes"; then
        print_success "Results contain detected_modes"
        if [ "$JQ_ENABLED" = true ]; then
            echo "$RESULTS" | jq '.spas'
        fi
    else
        print_error "Results missing detected_modes"
    fi
}

test_discovery_stop() {
    print_header "Testing Discovery Stop Functionality"
    
    print_test "Start quick discovery"
    curl -s -X POST "$WEB_URL/api/discovery/start" \
        -H "Content-Type: application/json" \
        -d '{"mode":"quick"}' > /dev/null
    
    sleep 3
    
    print_test "Stop discovery mid-execution"
    RESPONSE=$(curl -s -X POST "$WEB_URL/api/discovery/stop")
    
    if echo "$RESPONSE" | grep -q "stopped\|idle"; then
        print_success "Discovery stopped successfully"
    else
        print_info "Stop response: $RESPONSE"
        # This might be OK if discovery completed too fast
        STATUS=$(curl -s "$WEB_URL/api/discovery/status" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        if [ "$STATUS" = "idle" ] || [ "$STATUS" = "completed" ]; then
            print_success "Discovery already completed (too fast to catch)"
        else
            print_error "Discovery not stopped"
        fi
    fi
}

test_discovery_reset() {
    print_header "Testing Discovery Reset"
    
    print_test "Reset discovery state"
    RESPONSE=$(curl -s -X POST "$WEB_URL/api/discovery/reset")
    
    if echo "$RESPONSE" | grep -q "reset\|idle"; then
        print_success "Discovery state reset"
    else
        print_error "Discovery reset failed"
        echo "$RESPONSE"
    fi
    
    print_test "Verify state is idle"
    STATUS=$(curl -s "$WEB_URL/api/discovery/status" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    if [ "$STATUS" = "idle" ]; then
        print_success "State confirmed idle"
    else
        print_error "State not idle: $STATUS"
    fi
}

test_mqtt_topics() {
    print_header "Testing MQTT Topics"
    
    if [ "$MQTT_TESTS_ENABLED" != true ]; then
        print_info "Skipping MQTT tests (mosquitto_pub not installed)"
        return
    fi
    
    print_test "Subscribe to discovery status topic"
    print_info "Subscribing to: $MQTT_BASE_TOPIC/discovery/status"
    print_info "This will timeout after 10s if no messages..."
    
    timeout 10s mosquitto_sub -h "$MQTT_BROKER" -p "$MQTT_PORT" \
        -t "$MQTT_BASE_TOPIC/discovery/status" \
        -C 1 -v 2>/dev/null || true
    
    print_test "Start discovery via MQTT command"
    mosquitto_pub -h "$MQTT_BROKER" -p "$MQTT_PORT" \
        -t "$MQTT_BASE_TOPIC/discovery/control" \
        -m '{"action":"start","mode":"yaml_only"}'
    
    if [ $? -eq 0 ]; then
        print_success "MQTT command published"
        sleep 3
        
        # Check if discovery started
        STATUS=$(curl -s "$WEB_URL/api/discovery/status" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        if [ "$STATUS" = "running" ] || [ "$STATUS" = "completed" ]; then
            print_success "Discovery started via MQTT (status: $STATUS)"
        else
            print_error "Discovery not started via MQTT (status: $STATUS)"
        fi
    else
        print_error "MQTT command publish failed"
    fi
}

test_yaml_file() {
    print_header "Testing YAML File Generation"
    
    print_test "Check for discovered_items.yaml"
    if docker exec "$CONTAINER_NAME" test -f /config/discovered_items.yaml; then
        print_success "discovered_items.yaml exists"
        
        print_test "Verify YAML structure"
        YAML_CONTENT=$(docker exec "$CONTAINER_NAME" cat /config/discovered_items.yaml)
        
        if echo "$YAML_CONTENT" | grep -q "discovered_items:"; then
            print_success "YAML has correct root structure"
        else
            print_error "YAML missing discovered_items root"
        fi
        
        if echo "$YAML_CONTENT" | grep -q "detected_modes:"; then
            print_success "YAML contains detected_modes"
            print_info "Sample YAML content:"
            echo "$YAML_CONTENT" | head -20
        else
            print_info "No detected_modes found (may need to run full discovery first)"
        fi
    else
        print_error "discovered_items.yaml not found"
        print_info "Run a discovery first to generate the file"
    fi
}

test_startup_modes() {
    print_header "Testing Startup Modes"
    
    print_info "This test requires container restart and is optional"
    read -t 10 -p "Test startup modes? [y/N] " -n 1 -r || REPLY="N"
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Skipping startup mode tests"
        return
    fi
    
    # Test 1: startup_yaml
    print_test "Test DISCOVERY_MODE=startup_yaml"
    print_info "Setting DISCOVERY_MODE=startup_yaml..."
    
    # Backup current .env
    docker exec "$CONTAINER_NAME" cp /config/.env /config/.env.backup 2>/dev/null || true
    
    # Add DISCOVERY_MODE to .env
    docker exec "$CONTAINER_NAME" sh -c "echo 'DISCOVERY_MODE=startup_yaml' >> /config/.env"
    
    print_info "Restarting container..."
    docker-compose restart "$CONTAINER_NAME"
    
    print_info "Waiting for container to be ready..."
    sleep 10
    
    # Check logs
    LOGS=$(docker logs "$CONTAINER_NAME" --tail 50 2>&1)
    if echo "$LOGS" | grep -q "YAML Fallback\|Publishing detected_modes"; then
        print_success "Startup YAML publishing detected in logs"
    else
        print_info "YAML publishing not found in logs (check manually)"
    fi
    
    # Restore .env
    docker exec "$CONTAINER_NAME" sh -c "mv /config/.env.backup /config/.env 2>/dev/null || sed -i '/DISCOVERY_MODE=startup_yaml/d' /config/.env"
    
    print_info "Restored original configuration"
}

test_concurrent_operations() {
    print_header "Testing Concurrent Operation Prevention"
    
    print_test "Start first discovery"
    curl -s -X POST "$WEB_URL/api/discovery/start" \
        -H "Content-Type: application/json" \
        -d '{"mode":"quick"}' > /dev/null
    
    sleep 1
    
    print_test "Try to start second discovery (should fail)"
    RESPONSE=$(curl -s -X POST "$WEB_URL/api/discovery/start" \
        -H "Content-Type: application/json" \
        -d '{"mode":"quick"}')
    
    if echo "$RESPONSE" | grep -qi "already\|running"; then
        print_success "Concurrent start prevented"
    else
        print_error "Concurrent start not prevented"
        echo "$RESPONSE"
    fi
    
    # Cleanup
    curl -s -X POST "$WEB_URL/api/discovery/stop" > /dev/null
}

print_summary() {
    print_header "Test Summary"
    
    echo -e "Total Tests:  ${BLUE}$TESTS_TOTAL${NC}"
    echo -e "Passed:       ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Failed:       ${RED}$TESTS_FAILED${NC}"
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "\n${GREEN}🎉 All tests passed!${NC}"
        exit 0
    else
        echo -e "\n${RED}❌ Some tests failed${NC}"
        echo -e "${YELLOW}Check the output above for details${NC}"
        exit 1
    fi
}

# Main execution
main() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║  Background Discovery v0.3.0 - Manual Test Script     ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    check_prerequisites
    check_container
    test_webui_endpoints
    test_discovery_yaml_mode
    test_discovery_stop
    test_discovery_reset
    test_mqtt_topics
    test_yaml_file
    test_concurrent_operations
    
    # Optional longer tests
    test_discovery_quick_mode
    test_startup_modes
    
    print_summary
}

# Run main
main "$@"
