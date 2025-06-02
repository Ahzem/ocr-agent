# 🚀 Migration Steps: Old → Scalable OCR System

## Quick Start (Automated)

### Step 1: Run Migration Script
```bash
cd ocr
./migrate.sh
```

### Step 2: Test the System
```bash
./test_system.sh
```

### Step 3: Monitor Performance
```bash
# Install load testing tools
pip install locust

# Run load test
locust -f load_test.py --host=http://localhost
```

---

## Manual Step-by-Step (If Automated Fails)

### 1. Prerequisites Check
```bash
# Ensure Docker and Docker Compose are running
docker --version
docker-compose --version

# Check current system status
docker-compose ps
```

### 2. Stop Current System
```bash
docker-compose down
```

### 3. Backup Current Configuration
```bash
mkdir -p backup/$(date +%Y%m%d_%H%M%S)
cp app.py main.py docker-compose.yml nginx.conf Dockerfile backup/$(date +%Y%m%d_%H%M%S)/
```

### 4. Install Dependencies
```bash
# Add to requirements.txt
echo "
# Scalable version dependencies
fastapi==0.104.1
uvicorn[standard]==0.24.0
redis==5.0.1
aiofiles==23.2.1
aiohttp==3.9.1
psutil==5.9.6
uvloop==0.19.0
prometheus-client==0.19.0" >> requirements.txt
```

### 5. Replace Configuration Files
```bash
# Rename files
mv scalable_app.py new_app.py
mv docker-compose-scalable.yml docker-compose.yml
mv nginx-scalable.conf nginx.conf
```

### 6. Create Environment File
```bash
cat > .env << 'EOF'
GEMINI_API_KEY=AIzaSyCLXIu6Bf4WYsUDJTzjNqIHRzih5CN5Ngc
REDIS_URL=redis://redis:6379
MAX_CONCURRENT_EXTRACTIONS=50
MAX_MEMORY_USAGE_GB=8.0
API_RATE_LIMIT_PER_MINUTE=50
CACHE_TTL_HOURS=24
MAX_FILE_SIZE_MB=50
WORKER_PROCESSES=4
ENVIRONMENT=production
PYTHONPATH=/app
EOF
```

### 7. Create Dockerfile for Scalable Version
```bash
cat > Dockerfile.scalable << 'EOF'
FROM python:3.11-slim

RUN apt-get update && apt-get install -y curl gcc g++ && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY new_app.py app.py ./
RUN mkdir -p /cache /var/log/gunicorn

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "new_app:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop"]
EOF
```

### 8. Update Docker Compose References
```bash
sed -i 's/dockerfile: Dockerfile$/dockerfile: Dockerfile.scalable/g' docker-compose.yml
```

### 9. Build and Start New System
```bash
docker-compose build --no-cache
docker-compose up -d
```

### 10. Wait and Test
```bash
# Wait for services to start
sleep 60

# Test health endpoint
curl http://localhost/health

# Test processing endpoint
curl -X POST http://localhost/process-insurance-certificate \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/docs/test.pdf", "priority": 1}'
```

---

## Verification Checklist

After migration, verify these endpoints work:

### ✅ Basic Functionality
- [ ] Health check: `curl http://localhost/health`
- [ ] Processing: POST to `/process-insurance-certificate`
- [ ] Status check: GET `/status/{request_id}`

### ✅ Monitoring
- [ ] Prometheus: http://localhost:9090
- [ ] Grafana: http://localhost:3000 (admin/admin123)

### ✅ Load Testing
- [ ] Install: `pip install locust`
- [ ] Run: `locust -f load_test.py --host=http://localhost`

### ✅ Performance Metrics
- [ ] Response time < 30s for 95th percentile
- [ ] Memory usage < 80%
- [ ] No 5xx errors under normal load
- [ ] Cache hit rate > 70% (after warm-up)

---

## Troubleshooting

### Issue: Services Won't Start
```bash
# Check logs
docker-compose logs

# Check Docker resources
docker system df
docker system prune  # If needed
```

### Issue: Health Check Fails
```bash
# Check individual services
docker-compose ps
docker-compose logs redis
docker-compose logs ocr-service
```

### Issue: High Memory Usage
```bash
# Reduce concurrent extractions
# Edit docker-compose.yml:
# MAX_CONCURRENT_EXTRACTIONS=25
docker-compose restart
```

### Issue: Slow Performance
```bash
# Scale up services
docker-compose up -d --scale ocr-service=6

# Check Redis connection
docker-compose exec redis redis-cli ping
```

---

## Rollback (If Needed)

If something goes wrong:

```bash
./rollback.sh
```

Or manually:
```bash
docker-compose down
# Restore from backup/latest
docker-compose up -d
```

---

## Success Indicators

You'll know the migration succeeded when:

1. **Health endpoint returns 200**: `curl http://localhost/health`
2. **Processing returns request_id immediately**: Sub-second response
3. **Status endpoint tracks progress**: Shows queued → processing → completed
4. **No crashes under load**: System stays responsive
5. **Monitoring dashboards work**: Prometheus + Grafana accessible

---

## Next Steps After Migration

1. **Monitor Performance**: Watch dashboards for 24 hours
2. **Run Load Tests**: Gradually increase user load
3. **Tune Configuration**: Adjust based on actual usage patterns
4. **Set Up Alerts**: Configure monitoring alerts
5. **Document Changes**: Update team documentation

---

## Support

- **Logs**: `docker-compose logs -f`
- **Status**: `docker-compose ps`
- **Metrics**: `curl http://localhost/health`
- **Interactive testing**: Open http://localhost/docs

If you encounter issues, check the migration_guide.md for detailed troubleshooting steps. 