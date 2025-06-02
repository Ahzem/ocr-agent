# Migration Guide: Old → New Scalable OCR System

## Step 1: Backup Current System

```bash
# Create backup directory
mkdir -p backup/$(date +%Y%m%d_%H%M%S)

# Backup old files
cp app.py backup/$(date +%Y%m%d_%H%M%S)/
cp main.py backup/$(date +%Y%m%d_%H%M%S)/
cp docker-compose.yml backup/$(date +%Y%m%d_%H%M%S)/
cp nginx.conf backup/$(date +%Y%m%d_%H%M%S)/
cp Dockerfile backup/$(date +%Y%m%d_%H%M%S)/

echo "✅ Backup completed"
```

## Step 2: Install New Dependencies

```bash
# Update requirements.txt for scalable version
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
```

## Step 3: Create Missing Files

Create Dockerfile.scalable:
```dockerfile
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
COPY scalable_app.py .
COPY app.py .

# Create necessary directories
RUN mkdir -p /cache /var/log/gunicorn

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "scalable_app:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop"]
```

## Step 4: Replace Configuration Files

```bash
# Replace main files
mv scalable_app.py new_app.py
mv docker-compose-scalable.yml docker-compose.yml
mv nginx-scalable.conf nginx.conf

# Update any references
sed -i 's/scalable_app/new_app/g' docker-compose.yml
```

## Step 5: Environment Setup

Create `.env` file:
```env
# Gemini API
GEMINI_API_KEY=your_api_key_here

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
```

## Step 6: Testing Strategy

### Pre-Migration Tests
```bash
# Test old system (if still running)
curl -X POST "http://localhost/process" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/docs/test.pdf"}'
```

### Post-Migration Tests
```bash
# 1. Start new system
docker-compose up -d

# 2. Wait for services
sleep 30

# 3. Health check
curl http://localhost/health

# 4. Basic functionality test
curl -X POST "http://localhost/process-insurance-certificate" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/docs/test.pdf", "priority": 1}'

# 5. Check status
curl http://localhost/status/{request_id}
```

## Step 7: Load Testing

### Install Load Testing Tools
```bash
pip install locust httpx
```

### Create Load Test Script
```python
# load_test.py
from locust import HttpUser, task, between
import json
import random

class OCRUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        self.test_files = [
            "/docs/test1.pdf",
            "/docs/test2.pdf", 
            "/docs/test3.pdf"
        ]
    
    @task(3)
    def process_certificate(self):
        file_path = random.choice(self.test_files)
        response = self.client.post(
            "/process-insurance-certificate",
            json={"file_path": file_path, "priority": 1}
        )
        
        if response.status_code == 200:
            data = response.json()
            if "request_id" in data:
                # Check status
                self.client.get(f"/status/{data['request_id']}")
    
    @task(1)
    def health_check(self):
        self.client.get("/health")

# Run: locust -f load_test.py --host=http://localhost
```

## Step 8: Migration Execution

### Complete Migration Script
```bash
#!/bin/bash
# migrate.sh

set -e

echo "🚀 Starting OCR System Migration..."

# Step 1: Backup
echo "📦 Creating backup..."
BACKUP_DIR="backup/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR
cp app.py main.py docker-compose.yml nginx.conf Dockerfile $BACKUP_DIR/

# Step 2: Stop old services
echo "⏹️ Stopping old services..."
docker-compose down

# Step 3: Replace files
echo "🔄 Replacing configuration files..."
mv scalable_app.py new_app.py
mv docker-compose-scalable.yml docker-compose.yml
mv nginx-scalable.conf nginx.conf

# Step 4: Create Dockerfile for scalable version
cat > Dockerfile.scalable << 'EOF'
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl gcc g++ && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY new_app.py app.py ./
RUN mkdir -p /cache /var/log/gunicorn

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "new_app:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop"]
EOF

# Step 5: Update docker-compose references
sed -i 's/dockerfile: Dockerfile$/dockerfile: Dockerfile.scalable/g' docker-compose.yml

# Step 6: Build and start
echo "🏗️ Building new system..."
docker-compose build --no-cache

echo "🚀 Starting new system..."
docker-compose up -d

# Step 7: Wait for startup
echo "⏳ Waiting for services to start..."
sleep 60

# Step 8: Basic tests
echo "🧪 Running basic tests..."
curl -f http://localhost/health || { echo "❌ Health check failed"; exit 1; }

echo "✅ Migration completed successfully!"
echo "📊 Monitor system: docker-compose logs -f"
echo "📈 Metrics: http://localhost:9090 (Prometheus)"
echo "📊 Dashboard: http://localhost:3000 (Grafana)"
```

## Step 9: Testing Checklist

### ✅ Functional Tests
```bash
# Test 1: Health Check
curl http://localhost/health

# Test 2: Basic Processing
curl -X POST http://localhost/process-insurance-certificate \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/docs/test.pdf"}'

# Test 3: Status Check
curl http://localhost/status/{request_id}

# Test 4: System Metrics
curl http://localhost:9090/metrics
```

### ✅ Performance Tests
```bash
# Test 1: Load Test (100 users)
locust -f load_test.py --host=http://localhost -u 100 -r 10 -t 5m --headless

# Test 2: Concurrent Processing
for i in {1..20}; do
  curl -X POST http://localhost/process-insurance-certificate \
    -H "Content-Type: application/json" \
    -d '{"file_path": "/docs/test'$i'.pdf"}' &
done
wait

# Test 3: Memory Usage
docker stats --no-stream
```

### ✅ Reliability Tests
```bash
# Test 1: Redis Restart
docker-compose restart redis
sleep 10
curl http://localhost/health

# Test 2: Service Recovery
docker-compose stop ocr-service
sleep 5
docker-compose start ocr-service
sleep 30
curl http://localhost/health

# Test 3: High Load Recovery
# Run load test then check recovery
```

## Step 10: Monitoring Setup

### Grafana Dashboard Setup
```bash
# Import dashboards
curl -X POST http://admin:admin123@localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @grafana-dashboard.json
```

### Alert Configuration
```yaml
# prometheus-alerts.yml
groups:
- name: ocr_alerts
  rules:
  - alert: HighMemoryUsage
    expr: memory_usage_percent > 80
    for: 5m
    annotations:
      summary: "High memory usage detected"
  
  - alert: LowCacheHitRate
    expr: cache_hit_rate < 0.6
    for: 10m
    annotations:
      summary: "Cache hit rate below 60%"
```

## Step 11: Rollback Plan (if needed)

```bash
#!/bin/bash
# rollback.sh

echo "🔄 Rolling back to previous version..."

# Stop new system
docker-compose down

# Restore backup
LATEST_BACKUP=$(ls -t backup/ | head -n1)
cp backup/$LATEST_BACKUP/* .

# Start old system
docker-compose up -d

echo "✅ Rollback completed"
```

## Troubleshooting Common Issues

### Issue 1: Redis Connection Failed
```bash
# Check Redis status
docker-compose logs redis

# Restart Redis
docker-compose restart redis
```

### Issue 2: High Memory Usage
```bash
# Check memory usage
docker stats

# Reduce concurrent extractions
# Edit docker-compose.yml: MAX_CONCURRENT_EXTRACTIONS=25
```

### Issue 3: Slow Response Times
```bash
# Check queue size
curl http://localhost/health

# Scale up services
docker-compose up -d --scale ocr-service=6
```

## Success Metrics

After migration, you should see:
- ✅ Health check returns 200
- ✅ Processing requests return immediately with request_id
- ✅ Status endpoint shows processing progress
- ✅ 80%+ cache hit rate after warm-up
- ✅ No 5xx errors under normal load
- ✅ Memory usage < 80%
- ✅ Response times < 30s for 95th percentile 