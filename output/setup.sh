#!/bin/bash

echo "🚀 Setting up Insurance OCR API Production Environment"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker first:"
    echo "   https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose not found. Please install Docker Compose first:"
    echo "   https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✅ Docker and Docker Compose found"

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs cache nginx/logs nginx/ssl output

# Set permissions
chmod 755 logs cache nginx/logs output
chmod 700 nginx/ssl

# Create log files
touch logs/app.log logs/error.log
touch nginx/logs/access.log nginx/logs/error.log

echo "📊 Directory structure created:"
echo "   📁 logs/          - Application logs"
echo "   📁 cache/         - PDF cache storage"
echo "   📁 nginx/logs/    - Nginx logs"
echo "   📁 nginx/ssl/     - SSL certificates (if needed)"
echo "   📁 output/        - Processing output"

echo ""
echo "✅ Setup complete! Next steps:"
echo "   1. Run: docker-compose up --build"
echo "   2. Test: curl http://localhost/health"
echo "   3. Monitor: http://localhost:3000 (Grafana)"
echo "" 