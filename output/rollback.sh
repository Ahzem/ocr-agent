#!/bin/bash
# rollback.sh - Rollback to Previous OCR System Version

set -e

echo "🔄 Rolling back to previous OCR system version..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Confirm rollback
echo -e "${YELLOW}⚠️  This will rollback your OCR system to the previous version.${NC}"
echo -e "${YELLOW}⚠️  All current configuration will be replaced with backup.${NC}"
echo ""
read -p "Are you sure you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Rollback cancelled."
    exit 0
fi

# Find latest backup
log_info "Finding latest backup..."
if [ ! -d "backup" ]; then
    log_error "No backup directory found. Cannot rollback."
    exit 1
fi

LATEST_BACKUP=$(ls -t backup/ | head -n1)
if [ -z "$LATEST_BACKUP" ]; then
    log_error "No backup found. Cannot rollback."
    exit 1
fi

BACKUP_PATH="backup/$LATEST_BACKUP"
log_info "Found backup: $BACKUP_PATH"

# Stop current services
log_info "Stopping current services..."
if docker-compose ps | grep -q "Up"; then
    docker-compose down
    log_success "Services stopped"
else
    log_info "Services were not running"
fi

# Create rollback backup of current state
log_info "Creating rollback backup of current state..."
ROLLBACK_BACKUP_DIR="backup/rollback_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$ROLLBACK_BACKUP_DIR"

# Backup current files
[ -f "new_app.py" ] && cp new_app.py "$ROLLBACK_BACKUP_DIR/"
[ -f "docker-compose.yml" ] && cp docker-compose.yml "$ROLLBACK_BACKUP_DIR/"
[ -f "nginx.conf" ] && cp nginx.conf "$ROLLBACK_BACKUP_DIR/"
[ -f "Dockerfile.scalable" ] && cp Dockerfile.scalable "$ROLLBACK_BACKUP_DIR/"
[ -f ".env" ] && cp .env "$ROLLBACK_BACKUP_DIR/"

log_success "Current state backed up to $ROLLBACK_BACKUP_DIR"

# Restore old files
log_info "Restoring files from backup..."

# Remove new files
[ -f "new_app.py" ] && rm -f new_app.py
[ -f "Dockerfile.scalable" ] && rm -f Dockerfile.scalable
[ -f ".env" ] && rm -f .env

# Restore old files
if [ -f "$BACKUP_PATH/app.py" ]; then
    cp "$BACKUP_PATH/app.py" .
    log_success "Restored app.py"
fi

if [ -f "$BACKUP_PATH/main.py" ]; then
    cp "$BACKUP_PATH/main.py" .
    log_success "Restored main.py"
fi

if [ -f "$BACKUP_PATH/docker-compose.yml" ]; then
    cp "$BACKUP_PATH/docker-compose.yml" .
    log_success "Restored docker-compose.yml"
fi

if [ -f "$BACKUP_PATH/nginx.conf" ]; then
    cp "$BACKUP_PATH/nginx.conf" .
    log_success "Restored nginx.conf"
fi

if [ -f "$BACKUP_PATH/Dockerfile" ]; then
    cp "$BACKUP_PATH/Dockerfile" .
    log_success "Restored Dockerfile"
fi

# Clean up requirements.txt (remove scalable dependencies)
log_info "Cleaning up requirements.txt..."
if [ -f "requirements.txt" ]; then
    # Remove scalable dependencies section
    sed -i '/# Scalable version dependencies/,$d' requirements.txt
    log_success "Cleaned requirements.txt"
fi

# Rebuild and start old system
log_info "Building old system..."
if docker-compose build --no-cache > /dev/null 2>&1; then
    log_success "Build completed"
else
    log_error "Build failed"
    exit 1
fi

log_info "Starting old system..."
if docker-compose up -d; then
    log_success "Old system started"
else
    log_error "Failed to start old system"
    exit 1
fi

# Wait for system to be ready
log_info "Waiting for system to be ready..."
sleep 30

# Test if old system is working
if curl -f http://localhost/health > /dev/null 2>&1 || curl -f http://localhost/ > /dev/null 2>&1; then
    log_success "Old system is responding"
else
    log_warning "System may not be fully ready yet. Check logs: docker-compose logs"
fi

echo ""
log_success "Rollback completed successfully!"
echo ""
echo "📊 System Status:"
echo "- Backup restored from: $BACKUP_PATH"
echo "- Current system backed up to: $ROLLBACK_BACKUP_DIR"
echo "- Services status: docker-compose ps"
echo "- View logs: docker-compose logs -f"
echo ""
echo "🔄 To re-attempt migration:"
echo "- Fix any issues that caused the rollback"
echo "- Run: ./migrate.sh"
echo ""
echo "💡 Troubleshooting:"
echo "- Check service logs: docker-compose logs"
echo "- Verify configuration: cat docker-compose.yml"
echo "- Test endpoints: curl http://localhost/health" 