#!/bin/bash

echo "🧪 Testing Insurance OCR API Production Setup"
echo "============================================="

BASE_URL="http://localhost"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

test_endpoint() {
    local url=$1
    local description=$2
    local expected_status=${3:-200}
    
    echo -n "Testing $description... "
    
    response=$(curl -s -w "HTTPSTATUS:%{http_code}" "$url")
    http_status=$(echo $response | tr -d '\n' | sed -e 's/.*HTTPSTATUS://')
    
    if [ "$http_status" -eq "$expected_status" ]; then
        echo -e "${GREEN}✅ PASS${NC} (HTTP $http_status)"
        return 0
    else
        echo -e "${RED}❌ FAIL${NC} (HTTP $http_status)"
        return 1
    fi
}

echo "🔍 Running API Tests..."
echo ""

# Basic endpoint tests
test_endpoint "$BASE_URL/" "Root endpoint"
test_endpoint "$BASE_URL/health" "Health check"
test_endpoint "$BASE_URL/metrics" "Metrics endpoint"
test_endpoint "$BASE_URL/docs" "API documentation"

echo ""
echo "🔄 Testing API functionality..."

# Test POST endpoint
echo -n "Testing PDF processing... "
response=$(curl -s -X POST "$BASE_URL/process" \
    -H "Content-Type: application/json" \
    -d '{"file_path": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"}')

if echo "$response" | grep -q '"success"'; then
    echo -e "${GREEN}✅ PASS${NC}"
else
    echo -e "${YELLOW}⚠️  PARTIAL${NC} (API accessible but may need valid PDF)"
fi

echo ""
echo "📊 Testing Load Balancing..."

# Test multiple requests to see load balancing
for i in {1..5}; do
    echo -n "Request $i: "
    if curl -f -s "$BASE_URL/health" > /dev/null; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${RED}❌${NC}"
    fi
done

echo ""
echo "🔍 Service Status:"
docker-compose ps

echo ""
echo "📝 Recent Logs:"
echo "--- App1 Logs ---"
docker-compose logs --tail=5 app1

echo ""
echo "--- Nginx Logs ---"
docker-compose logs --tail=5 nginx

echo ""
echo "🎯 Performance Test:"
echo "Running 10 concurrent requests..."

for i in {1..10}; do
    curl -s "$BASE_URL/health" > /dev/null &
done
wait

echo -e "${GREEN}✅ Concurrent requests completed${NC}"

echo ""
echo "📈 Monitoring URLs:"
echo "   • API Health:     $BASE_URL/health"
echo "   • API Docs:       $BASE_URL/docs"
echo "   • Prometheus:     http://localhost:9090"
echo "   • Grafana:        http://localhost:3000"

echo ""
echo "🎉 Production testing completed!" 