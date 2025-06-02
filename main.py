from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Union
import time
import asyncio
import redis
import json
import hashlib
from datetime import datetime, timedelta
import logging
import os

# Import our PDF processing function
from app import process_insurance_certificate

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Redis connection for caching and rate limiting
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("Redis connected successfully")
except Exception as e:
    logger.warning(f"Redis connection failed: {e}")
    redis_client = None

app = FastAPI(
    title="Insurance Certificate OCR API",
    version="2.0.0",
    description="Production-ready API for processing insurance certificates with OCR",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Security middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure for your domain in production
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure specific origins in production
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Request models
class ProcessRequest(BaseModel):
    file_path: str
    priority: str = "normal"  # normal, high
    
class URLProcessRequest(BaseModel):
    url: HttpUrl
    priority: str = "normal"

# Rate limiting middleware
async def rate_limit_middleware(request: Request, call_next):
    if redis_client:
        client_ip = request.client.host
        current_time = datetime.now()
        window_start = current_time.replace(second=0, microsecond=0)
        
        # Rate limit: 100 requests per minute per IP
        key = f"rate_limit:{client_ip}:{window_start.isoformat()}"
        current_requests = redis_client.get(key)
        
        if current_requests and int(current_requests) >= 100:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Maximum 100 requests per minute."
            )
        
        # Increment counter
        redis_client.incr(key)
        redis_client.expire(key, 60)
    
    response = await call_next(request)
    return response

app.middleware("http")(rate_limit_middleware)

# Background task processing
async def process_certificate_async(file_path: str, request_id: str):
    """Process certificate in background and cache result"""
    try:
        logger.info(f"Starting async processing for request {request_id}")
        result = process_insurance_certificate(file_path)
        
        # Cache result for 1 hour
        if redis_client:
            cache_key = f"result:{request_id}"
            redis_client.setex(
                cache_key, 
                3600,  # 1 hour
                json.dumps(result)
            )
        
        logger.info(f"Completed async processing for request {request_id}")
        return result
        
    except Exception as e:
        logger.error(f"Async processing failed for {request_id}: {e}")
        if redis_client:
            error_result = {
                "success": False,
                "error": f"Async processing error: {str(e)}",
                "file_path": file_path
            }
            cache_key = f"result:{request_id}"
            redis_client.setex(cache_key, 3600, json.dumps(error_result))

@app.get("/")
def root():
    return {
        "message": "Insurance Certificate OCR API v2.0 🚀",
        "status": "production",
        "endpoints": {
            "/process": "POST - Process PDF (sync)",
            "/process-async": "POST - Process PDF (async)",
            "/result/{request_id}": "GET - Get async result",
            "/health": "GET - Health check",
            "/metrics": "GET - System metrics"
        }
    }

@app.get("/health")
def health_check():
    """Comprehensive health check"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "redis": "connected" if redis_client else "disconnected",
            "gemini_api": "available"  # You can add actual API check
        }
    }
    
    # Check Redis
    if redis_client:
        try:
            redis_client.ping()
            health_status["services"]["redis"] = "connected"
        except:
            health_status["services"]["redis"] = "disconnected"
            health_status["status"] = "degraded"
    
    return health_status

@app.get("/metrics")
def get_metrics():
    """System metrics for monitoring"""
    metrics = {
        "timestamp": datetime.now().isoformat(),
        "requests_processed": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "errors": 0
    }
    
    if redis_client:
        try:
            # Get metrics from Redis
            metrics["requests_processed"] = int(redis_client.get("metrics:requests") or 0)
            metrics["cache_hits"] = int(redis_client.get("metrics:cache_hits") or 0)
            metrics["cache_misses"] = int(redis_client.get("metrics:cache_misses") or 0)
            metrics["errors"] = int(redis_client.get("metrics:errors") or 0)
        except:
            pass
    
    return metrics

def generate_request_id(file_path: str) -> str:
    """Generate unique request ID"""
    timestamp = str(int(time.time() * 1000))
    content = f"{file_path}:{timestamp}"
    return hashlib.md5(content.encode()).hexdigest()[:12]

@app.post("/process")
async def process_certificate(request: ProcessRequest):
    """Synchronous processing - for immediate results"""
    start_time = time.time()
    
    try:
        # Check cache first
        cache_key = f"cache:{hashlib.md5(request.file_path.encode()).hexdigest()}"
        if redis_client:
            cached_result = redis_client.get(cache_key)
            if cached_result:
                redis_client.incr("metrics:cache_hits")
                result = json.loads(cached_result)
                logger.info(f"Cache hit for {request.file_path}")
                
                if result["success"]:
                    return {
                        "success": True,
                        "message": "Certificate processed successfully (cached)",
                        "data": [result["data"]],
                        "processing_info": result.get("processing_info", {}),
                        "cached": True
                    }
        
        # Process the certificate
        if redis_client:
            redis_client.incr("metrics:cache_misses")
            redis_client.incr("metrics:requests")
        
        result = process_insurance_certificate(request.file_path)
        
        # Cache successful results
        if result["success"] and redis_client:
            redis_client.setex(cache_key, 1800, json.dumps(result))  # 30 minutes
        
        processing_time = time.time() - start_time
        
        if result["success"]:
            formatted_data = [result["data"]]
            return {
                "success": True,
                "message": "Certificate processed successfully",
                "data": formatted_data,
                "processing_info": {
                    **result.get("processing_info", {}),
                    "total_processing_time": processing_time
                },
                "cached": False
            }
        else:
            if redis_client:
                redis_client.incr("metrics:errors")
            raise HTTPException(
                status_code=400,
                detail=result["error"]
            )
            
    except Exception as e:
        if redis_client:
            redis_client.incr("metrics:errors")
        logger.error(f"Processing error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Processing error: {str(e)}"
        )

@app.post("/process-async")
async def process_certificate_async_endpoint(request: ProcessRequest, background_tasks: BackgroundTasks):
    """Asynchronous processing - returns immediately with request ID"""
    try:
        request_id = generate_request_id(request.file_path)
        
        # Add to background tasks
        background_tasks.add_task(
            process_certificate_async,
            request.file_path,
            request_id
        )
        
        if redis_client:
            redis_client.incr("metrics:requests")
        
        return {
            "success": True,
            "message": "Processing started",
            "request_id": request_id,
            "status_url": f"/result/{request_id}",
            "estimated_completion": (datetime.now() + timedelta(minutes=2)).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Async processing setup error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start processing: {str(e)}"
        )

@app.get("/result/{request_id}")
async def get_async_result(request_id: str):
    """Get result of async processing"""
    if not redis_client:
        raise HTTPException(
            status_code=503,
            detail="Redis not available for async processing"
        )
    
    try:
        cache_key = f"result:{request_id}"
        result_data = redis_client.get(cache_key)
        
        if not result_data:
            return {
                "status": "processing",
                "message": "Processing in progress or request not found",
                "request_id": request_id
            }
        
        result = json.loads(result_data)
        
        if result["success"]:
            return {
                "status": "completed",
                "success": True,
                "data": [result["data"]],
                "processing_info": result.get("processing_info", {}),
                "request_id": request_id
            }
        else:
            return {
                "status": "failed",
                "success": False,
                "error": result["error"],
                "request_id": request_id
            }
            
    except Exception as e:
        logger.error(f"Error getting async result: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving result: {str(e)}"
        )

# Legacy endpoints
@app.post("/process-url")
async def process_certificate_from_url(request: URLProcessRequest):
    """Process from URL - legacy endpoint"""
    process_request = ProcessRequest(file_path=str(request.url), priority=request.priority)
    return await process_certificate(process_request)

@app.get("/run-script")
def run_script():
    """Legacy endpoint"""
    return {
        "message": "This endpoint is deprecated. Use POST /process instead.",
        "documentation": "/docs"
    }
