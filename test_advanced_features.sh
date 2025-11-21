#!/bin/bash
# Test Script for Advanced Features APIs
# Run this to test all the new endpoints

HOST="http://localhost:8080"

echo "========================================="
echo "Testing Advanced Features APIs"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to test an endpoint
test_endpoint() {
    local name="$1"
    local url="$2"

    echo -e "${YELLOW}Testing: $name${NC}"
    echo "URL: $url"

    response=$(curl -s -w "\n%{http_code}" "$url")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}✓ SUCCESS${NC} (HTTP $http_code)"
        echo "$body" | jq '.' 2>/dev/null || echo "$body"
    else
        echo -e "${RED}✗ FAILED${NC} (HTTP $http_code)"
        echo "$body"
    fi
    echo ""
    echo "-----------------------------------------"
    echo ""
}

# Test 1: Camera Groups - List All
test_endpoint "1. List All Camera Groups" \
    "$HOST/api/groups/list"

# Test 2: Camera Groups - Get I-10 Cameras
test_endpoint "2. Get I-10 Highway Cameras" \
    "$HOST/api/groups/highway/I-10"

# Test 3: Camera Groups - Get Okaloosa County Cameras
test_endpoint "3. Get Okaloosa County Cameras" \
    "$HOST/api/groups/county/Okaloosa"

# Test 4: Search - Find cameras with "I10" in name
test_endpoint "4. Search for 'I10' cameras" \
    "$HOST/api/cameras/search?q=I10"

# Test 5: Search - Get all offline cameras
test_endpoint "5. Get All Offline Cameras" \
    "$HOST/api/cameras/search?status=offline"

# Test 6: Search - Filter by highway and status
test_endpoint "6. Get Online I-10 Cameras" \
    "$HOST/api/cameras/search?highway=I-10&status=online"

# Test 7: SLA Compliance (30 days, 95% target)
test_endpoint "7. Get SLA Compliance Report" \
    "$HOST/api/sla/compliance?days=30&target=95.0"

# Test 8: Downtime Stats for specific camera
test_endpoint "8. Get Downtime Stats for CCTV-I10-012.4-EB" \
    "$HOST/api/downtime/stats/CCTV-I10-012.4-EB?days=30"

# Test 9: System Summary
test_endpoint "9. Get System Summary" \
    "$HOST/api/stats/summary"

# Test 10: Upcoming Maintenance
test_endpoint "10. Get Upcoming Maintenance" \
    "$HOST/api/maintenance/upcoming?days=7"

# Test 11: Check Maintenance Window
test_endpoint "11. Check if Camera in Maintenance" \
    "$HOST/api/maintenance/check/CCTV-I10-012.4-EB"

echo ""
echo "========================================="
echo "Testing Complete!"
echo "========================================="
echo ""
echo "Quick Test Commands:"
echo ""
echo "# List all groups:"
echo "curl $HOST/api/groups/list | jq"
echo ""
echo "# Search offline cameras:"
echo "curl '$HOST/api/cameras/search?status=offline' | jq"
echo ""
echo "# Get SLA report:"
echo "curl '$HOST/api/sla/compliance?days=30&target=95.0' | jq"
echo ""
echo "# System summary:"
echo "curl $HOST/api/stats/summary | jq"
echo ""
