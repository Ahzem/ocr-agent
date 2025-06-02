#!/bin/bash

set -e  # Exit on any error

echo "🚀 Insurance OCR API Production Deployment"
echo "==========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "\n${BLUE}==== $1 ====${NC}"
}

# Step 1: Check prerequisites
print_step "Checking Prerequisites"
if ! command -v docker &> /dev/null; then
    print_error "Docker not found. Install from: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose not found. Install from: https://docs.docker.com/compose/install/"
    exit 1
fi

print_status "Docker and Docker Compose are installed ✅"

# Step 2: Setup directories
print_step "Setting Up Directory Structure"
mkdir -p logs cache nginx/logs nginx/ssl output
chmod 755 logs cache nginx/logs output
chmod 700 nginx/ssl

# Create initial log files
touch logs/app.log logs/error.log nginx/logs/access.log nginx/logs/error.log

print_status "Directories created ✅"

# Step 3: Build and deploy
print_step "Building and Deploying Services"

print_status "Stopping any existing services..."
docker-compose down --remove-orphans 2>/dev/null || true

print_status "Building Docker images..."
docker-compose build --no-cache

print_status "Starting services..."
docker-compose up -d

# Step 4: Wait for services
print_step "Waiting for Services to Start"

print_status "Waiting for services to be ready..."
sleep 30

# Step 5: Test services
print_step "Testing Services"

if curl -f -s http://localhost/health > /dev/null; then
    print_status "API Health Check: ✅"
else
    print_error "API Health Check: ❌"
    print_status "Checking logs..."
    docker-compose logs app1
fi

# Step 6: Display information
print_step "Deployment Complete!"

echo -e "\n${GREEN}🎉 Services are running!${NC}\n"

echo "📊 Service URLs:"
echo "   • API Health:     http://localhost/health"
echo "   • API Docs:       http://localhost/docs"
echo "   • Prometheus:     http://localhost:9090"
echo "   • Grafana:        http://localhost:3000"
echo ""

echo "🔧 Management Commands:"
echo "   • View logs:      docker-compose logs -f"
echo "   • Scale up:       docker-compose up --scale app1=2 -d"
echo "   • Stop services:  docker-compose down"
echo ""

echo "📈 Service Status:"
docker-compose ps

print_status "Deployment completed! 🚀" 