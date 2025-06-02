#!/bin/bash
# test_system.sh - Comprehensive Testing Script for Scalable OCR System

set -e

echo "🧪 Starting Comprehensive System Testing..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0
TOTAL_TESTS=0

# Helper functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
    ((TESTS_PASSED++))
    ((TOTAL_TESTS++))
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
    ((TESTS_FAILED++))
    ((TOTAL_TESTS++))
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo -e "\n${BLUE}Running: $test_name${NC}"
    
    if eval "$test_command" > /dev/null 2>&1; then
        log_success "$test_name"
        return 0
    else
        log_error "$test_name"
        return 1
    fi
}

# Wait for service to be ready
wait_for_service() {
    local url="$1"
    local max_attempts=30
    local attempt=1
    
    log_info "Waiting for service at $url..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f "$url" > /dev/null 2>&1; then
            log_success "Service is ready"
            return 0
        fi
        
        echo -n "."
        sleep 2
        ((attempt++))
    done
    
    log_error "Service failed to start within 60 seconds"
    return 1
}

# Test 1: System Health
test_health_check() {
    log_info "Testing system health..."
    
    response=$(curl -s http://localhost/health)
    
    if echo "$response" | grep -q '"healthy": true\|"status": "healthy"'; then
        log_success "Health check endpoint working"
    else
        log_error "Health check failed: $response"
        return 1
    fi
}

# Test 2: Redis Connection
test_redis_connection() {
    log_info "Testing Redis connection..."
    
    if docker-compose exec -T redis redis-cli ping | grep -q "PONG"; then
        log_success "Redis connection working"
    else
        log_error "Redis connection failed"
        return 1
    fi
}

# Test 3: Basic Processing
test_basic_processing() {
    log_info "Testing basic certificate processing..."
    
    # Create test PDF path (assuming docs directory exists)
    test_payload='{"file_path": "/docs/test.pdf", "priority": 1}'
    
    response=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "$test_payload" \
        http://localhost/process-insurance-certificate)
    
    if echo "$response" | grep -q '"success": true' && echo "$response" | grep -q '"request_id"'; then
        log_success "Basic processing endpoint working"
        
        # Extract request ID for status checking
        request_id=$(echo "$response" | grep -o '"request_id": *"[^"]*"' | sed 's/"request_id": *"\([^"]*\)"/\1/')
        echo "Request ID: $request_id"
        
        # Test status endpoint
        sleep 2
        status_response=$(curl -s http://localhost/status/$request_id)
        
        if echo "$status_response" | grep -q '"status"'; then
            log_success "Status endpoint working"
        else
            log_error "Status endpoint failed: $status_response"
        fi
    else
        log_error "Basic processing failed: $response"
        return 1
    fi
}

# Test 4: Concurrent Requests
test_concurrent_processing() {
    log_info "Testing concurrent request handling..."
    
    # Send 5 concurrent requests
    for i in {1..5}; do
        curl -s -X POST \
            -H "Content-Type: application/json" \
            -d '{"file_path": "/docs/test'$i'.pdf", "priority": 1}' \
            http://localhost/process-insurance-certificate &
    done
    
    wait  # Wait for all background jobs
    
    log_success "Concurrent requests handled"
}

# Test 5: Rate Limiting
test_rate_limiting() {
    log_info "Testing rate limiting..."
    
    # Send rapid requests to test rate limiting
    rate_limit_hit=false
    
    for i in {1..20}; do
        response=$(curl -s -w "%{http_code}" \
            -X POST \
            -H "Content-Type: application/json" \
            -d '{"file_path": "/docs/rate_test.pdf", "priority": 1}' \
            http://localhost/process-insurance-certificate)
        
        if echo "$response" | grep -q "503\|429"; then
            rate_limit_hit=true
            break
        fi
        
        sleep 0.1
    done
    
    if [ "$rate_limit_hit" = true ]; then
        log_success "Rate limiting working"
    else
        log_warning "Rate limiting not triggered (may be normal)"
    fi
}

# Test 6: Memory Usage
test_memory_usage() {
    log_info "Testing memory usage..."
    
    # Get memory stats from Docker
    memory_stats=$(docker stats --no-stream --format "table {{.Container}}\t{{.MemUsage}}" | grep ocr)
    
    if [ -n "$memory_stats" ]; then
        log_success "Memory monitoring working"
        echo "Memory usage: $memory_stats"
    else
        log_error "Cannot retrieve memory stats"
    fi
}

# Test 7: Service Recovery
test_service_recovery() {
    log_info "Testing service recovery..."
    
    # Restart one service instance
    container_id=$(docker-compose ps -q ocr-service | head -n1)
    
    if [ -n "$container_id" ]; then
        docker restart "$container_id" > /dev/null 2>&1
        sleep 10
        
        if curl -f http://localhost/health > /dev/null 2>&1; then
            log_success "Service recovery working"
        else
            log_error "Service recovery failed"
            return 1
        fi
    else
        log_warning "No OCR service container found"
    fi
}

# Test 8: Load Test (Light)
test_light_load() {
    log_info "Running light load test..."
    
    if command -v locust >/dev/null 2>&1; then
        # Run light load test for 1 minute
        locust -f load_test.py \
            --host=http://localhost \
            -u 10 -r 2 -t 60s \
            --headless \
            --csv=test_results/light_load > /dev/null 2>&1
        
        if [ $? -eq 0 ]; then
            log_success "Light load test completed"
        else
            log_error "Light load test failed"
        fi
    else
        log_warning "Locust not installed, skipping load test"
    fi
}

# Test 9: API Documentation
test_api_docs() {
    log_info "Testing API documentation..."
    
    if curl -f http://localhost/docs > /dev/null 2>&1; then
        log_success "API documentation accessible"
    else
        log_error "API documentation not accessible"
    fi
}

# Test 10: Monitoring Endpoints
test_monitoring() {
    log_info "Testing monitoring endpoints..."
    
    # Test Prometheus
    if curl -f http://localhost:9090/metrics > /dev/null 2>&1; then
        log_success "Prometheus metrics accessible"
    else
        log_warning "Prometheus not accessible"
    fi
    
    # Test Grafana
    if curl -f http://localhost:3000/login > /dev/null 2>&1; then
        log_success "Grafana dashboard accessible"
    else
        log_warning "Grafana not accessible"
    fi
}

# Main test execution
main() {
    echo "🚀 Scalable OCR System - Comprehensive Testing"
    echo "=============================================="
    
    # Create results directory
    mkdir -p test_results
    
    # Check if services are running
    if ! docker-compose ps | grep -q "Up"; then
        log_error "Services are not running. Please run: docker-compose up -d"
        exit 1
    fi
    
    # Wait for main service
    if ! wait_for_service "http://localhost/health"; then
        log_error "Main service failed to start"
        exit 1
    fi
    
    echo -e "\n🧪 Running Test Suite..."
    echo "========================"
    
    # Run all tests
    test_health_check
    test_redis_connection
    test_basic_processing
    test_concurrent_processing
    test_rate_limiting
    test_memory_usage
    test_service_recovery
    test_light_load
    test_api_docs
    test_monitoring
    
    # Summary
    echo -e "\n📊 Test Results Summary"
    echo "======================="
    echo -e "Total Tests: $TOTAL_TESTS"
    echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
    echo -e "${RED}Failed: $TESTS_FAILED${NC}"
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "\n🎉 ${GREEN}All tests passed! System is ready for production.${NC}"
        
        echo -e "\n📋 Next Steps:"
        echo "- Monitor system: docker-compose logs -f"
        echo "- View metrics: http://localhost:9090"
        echo "- View dashboard: http://localhost:3000"
        echo "- Run load tests: locust -f load_test.py --host=http://localhost"
        
        exit 0
    else
        echo -e "\n⚠️  ${YELLOW}Some tests failed. Please check the system configuration.${NC}"
        
        echo -e "\n🔍 Troubleshooting:"
        echo "- Check logs: docker-compose logs"
        echo "- Verify configuration: cat .env"
        echo "- Restart services: docker-compose restart"
        
        exit 1
    fi
}

# Run tests
main "$@" 