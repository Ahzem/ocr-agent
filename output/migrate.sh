#!/bin/bash
# migrate.sh - OCR System Migration Script

set -e

echo "🚀 Starting OCR System Migration..."

# Step 1: Backup
echo "📦 Creating backup..."
BACKUP_DIR="backup/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

# Backup old files if they exist
[ -f "app.py" ] && cp app.py $BACKUP_DIR/
[ -f "main.py" ] && cp main.py $BACKUP_DIR/
[ -f "docker-compose.yml" ] && cp docker-compose.yml $BACKUP_DIR/
[ -f "nginx.conf" ] && cp nginx.conf $BACKUP_DIR/
[ -f "Dockerfile" ] && cp Dockerfile $BACKUP_DIR/

echo "✅ Backup created in $BACKUP_DIR"

# Step 2: Stop old services
echo "⏹️ Stopping old services..."
if docker-compose ps | grep -q "Up"; then
    docker-compose down
fi

# Step 3: Update requirements.txt
echo "📦 Updating dependencies..."
cat >> requirements.txt << 'EOF'

# Scalable version dependencies
fastapi==0.104.1
uvicorn[standard]==0.24.0
redis==5.0.1
aiofiles==23.2.1
aiohttp==3.9.1
psutil==5.9.6
uvloop==0.19.0
prometheus-client==0.19.0
EOF

# Step 4: Replace configuration files
echo "🔄 Replacing configuration files..."

# Rename scalable files to main files
if [ -f "scalable_app.py" ]; then
    mv scalable_app.py new_app.py
fi

if [ -f "docker-compose-scalable.yml" ]; then
    mv docker-compose-scalable.yml docker-compose.yml
fi

if [ -f "nginx-scalable.conf" ]; then
    mv nginx-scalable.conf nginx.conf
fi

# Step 5: Create Dockerfile for scalable version
echo "🐳 Creating new Dockerfile..."
cat > Dockerfile.scalable << 'EOF'
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY new_app.py .
COPY app.py .

# Create necessary directories
RUN mkdir -p /cache /var/log/gunicorn

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "new_app:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop"]
EOF

# Step 6: Create environment file
echo "⚙️ Creating environment configuration..."
cat > .env << 'EOF'
# Gemini API
GEMINI_API_KEY=AIzaSyCLXIu6Bf4WYsUDJTzjNqIHRzih5CN5Ngc

# Redis
REDIS_URL=redis://redis:6379

# Scalability Settings
MAX_CONCURRENT_EXTRACTIONS=50
MAX_MEMORY_USAGE_GB=8.0
API_RATE_LIMIT_PER_MINUTE=50
CACHE_TTL_HOURS=24
MAX_FILE_SIZE_MB=50
WORKER_PROCESSES=4

# Environment
ENVIRONMENT=production
PYTHONPATH=/app
EOF

# Step 7: Update docker-compose references
echo "🔧 Updating Docker Compose configuration..."
sed -i 's/dockerfile: Dockerfile$/dockerfile: Dockerfile.scalable/g' docker-compose.yml
sed -i 's/scalable_app:app/new_app:app/g' docker-compose.yml

# Step 8: Build and start
echo "🏗️ Building new system..."
docker-compose build --no-cache

echo "🚀 Starting new system..."
docker-compose up -d

# Step 9: Wait for startup
echo "⏳ Waiting for services to start..."
sleep 60

# Step 10: Basic tests
echo "🧪 Running basic tests..."

# Test health endpoint
if curl -f http://localhost/health > /dev/null 2>&1; then
    echo "✅ Health check passed"
else
    echo "❌ Health check failed"
    echo "📊 Checking service status..."
    docker-compose ps
    echo "📋 Recent logs..."
    docker-compose logs --tail=20
    exit 1
fi

# Test Redis connection
if curl -s http://localhost/health | grep -q "redis"; then
    echo "✅ Redis connection verified"
else
    echo "⚠️ Redis connection may have issues"
fi

echo ""
echo "✅ Migration completed successfully!"
echo ""
echo "📊 Monitoring URLs:"
echo "   Health Check:  http://localhost/health"
echo "   Prometheus:    http://localhost:9090"
echo "   Grafana:       http://localhost:3000 (admin/admin123)"
echo ""
echo "📋 Useful commands:"
echo "   Monitor logs:  docker-compose logs -f"
echo "   Check status:  docker-compose ps"
echo "   View metrics:  curl http://localhost/health"
echo ""
echo "🔄 If issues occur, run: ./rollback.sh" 