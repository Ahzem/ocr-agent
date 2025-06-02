import asyncio
import aiofiles
import aiohttp
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.concurrency import run_in_threadpool
import uvicorn
from concurrent.futures import ProcessPoolExecutor
import psutil
import json
import os
from typing import Dict, Any, Optional
import logging
from datetime import datetime, timedelta
import hashlib
from dataclasses import dataclass
import signal
import sys

# Enhanced scalable configuration
@dataclass
class ScalabilityConfig:
    max_concurrent_extractions: int = 50  # Limit concurrent PDF processing
    max_memory_usage_gb: float = 8.0      # Memory limit
    api_rate_limit_per_minute: int = 50   # Conservative Gemini API rate
    cache_ttl_hours: int = 24             # Result cache TTL
    request_timeout_seconds: int = 300    # Max processing time
    max_file_size_mb: int = 50            # PDF size limit
    worker_processes: int = 4             # For CPU-intensive tasks

config = ScalabilityConfig()

# Global resources
app = FastAPI(title="Scalable Insurance OCR API")
redis_pool = None
api_semaphore = None
extraction_semaphore = None
process_pool = None
session = None

# Request queue for rate limiting
request_queue = asyncio.Queue(maxsize=1000)
processing_tasks = set()

@dataclass
class ProcessingRequest:
    request_id: str
    file_path: str
    priority: int = 1
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

class ResourceManager:
    """Manage system resources and prevent overload"""
    
    @staticmethod
    async def check_memory_usage() -> bool:
        """Check if memory usage is within limits"""
        memory = psutil.virtual_memory()
        current_gb = memory.used / (1024**3)
        return current_gb < config.max_memory_usage_gb
    
    @staticmethod
    async def check_system_health() -> Dict[str, Any]:
        """Get system health metrics"""
        memory = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1)
        
        return {
            "memory_usage_gb": memory.used / (1024**3),
            "memory_percent": memory.percent,
            "cpu_percent": cpu,
            "active_extractions": len(processing_tasks),
            "queue_size": request_queue.qsize(),
            "healthy": (
                memory.percent < 80 and 
                cpu < 90 and 
                len(processing_tasks) < config.max_concurrent_extractions
            )
        }

class CacheManager:
    """Async Redis cache for processed results"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def get_cached_result(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached extraction result"""
        try:
            cached = await self.redis.get(f"ocr:result:{file_hash}")
            if cached:
                return json.loads(cached)
        except Exception as e:
            logging.error(f"Cache get error: {e}")
        return None
    
    async def cache_result(self, file_hash: str, result: Dict[str, Any]):
        """Cache extraction result"""
        try:
            await self.redis.setex(
                f"ocr:result:{file_hash}",
                config.cache_ttl_hours * 3600,
                json.dumps(result)
            )
        except Exception as e:
            logging.error(f"Cache set error: {e}")
    
    async def get_request_status(self, request_id: str) -> Optional[str]:
        """Get processing request status"""
        try:
            return await self.redis.get(f"ocr:status:{request_id}")
        except:
            return None
    
    async def set_request_status(self, request_id: str, status: str):
        """Set processing request status"""
        try:
            await self.redis.setex(f"ocr:status:{request_id}", 3600, status)
        except Exception as e:
            logging.error(f"Status set error: {e}")

class APIRateLimiter:
    """Rate limiting for external API calls"""
    
    def __init__(self):
        self.call_times = []
        self.lock = asyncio.Lock()
    
    async def acquire(self) -> bool:
        """Acquire permission for API call"""
        async with self.lock:
            now = datetime.now()
            # Remove calls older than 1 minute
            self.call_times = [t for t in self.call_times if now - t < timedelta(minutes=1)]
            
            if len(self.call_times) < config.api_rate_limit_per_minute:
                self.call_times.append(now)
                return True
            return False
    
    async def wait_for_slot(self):
        """Wait until API call slot is available"""
        while not await self.acquire():
            await asyncio.sleep(1)

# Global instances
rate_limiter = APIRateLimiter()
cache_manager = None

async def process_pdf_async(file_path: str) -> tuple:
    """Async wrapper for CPU-intensive PDF processing"""
    # Run the existing PDF processing in a separate process
    # to avoid blocking the event loop
    
    def _process_pdf_sync(path):
        # Import the heavy processing function here to avoid import in main thread
        from app import process_pdf_optimized
        return process_pdf_optimized(path)
    
    # Use process pool for CPU-intensive work
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(process_pool, _process_pdf_sync, file_path)
    return result

async def call_gemini_api_async(prompt: str) -> str:
    """Async Gemini API call with rate limiting"""
    # Wait for API rate limit slot
    await rate_limiter.wait_for_slot()
    
    # Use existing Gemini code but wrap in async
    def _call_gemini_sync(prompt_text):
        from app import model
        response = model.generate_content(prompt_text)
        return response.text
    
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _call_gemini_sync, prompt)
    return result

async def process_single_request(request: ProcessingRequest) -> Dict[str, Any]:
    """Process a single OCR request with full async handling"""
    try:
        # Set status to processing
        await cache_manager.set_request_status(request.request_id, "processing")
        
        # Check memory before processing
        if not await ResourceManager.check_memory_usage():
            raise HTTPException(
                status_code=503, 
                detail="System memory limit reached. Please try again later."
            )
        
        # Generate file hash for caching
        async with aiofiles.open(request.file_path, 'rb') as f:
            file_content = await f.read()
            file_hash = hashlib.md5(file_content).hexdigest()
        
        # Check cache first
        cached_result = await cache_manager.get_cached_result(file_hash)
        if cached_result:
            await cache_manager.set_request_status(request.request_id, "completed")
            return {
                "success": True,
                "data": cached_result,
                "source": "cache",
                "request_id": request.request_id
            }
        
        # Process PDF asynchronously
        pdf_text, fitz_text, plumber_text = await process_pdf_async(request.file_path)
        
        # Use intelligent chunking from original code
        from app import intelligent_chunking
        optimized_text = intelligent_chunking(pdf_text, max_chars=6000)
        
        # Build enhanced prompt
        prompt = f"""[Enhanced prompt from original code...]
        Document Text:
        {optimized_text}
        """
        
        # Call Gemini API asynchronously with rate limiting
        response_text = await call_gemini_api_async(prompt)
        
        # Parse and validate response
        try:
            clean_response = response_text.strip()
            if clean_response.startswith('```'):
                clean_response = clean_response.split('\n', 1)[1].rsplit('\n```', 1)[0]
            
            structured_data = json.loads(clean_response)
            
            # Apply validation pipeline (run in thread pool to avoid blocking)
            from app import validate_extraction
            validated_data = await run_in_threadpool(
                validate_extraction, 
                structured_data, 
                pdf_text, 
                fitz_text, 
                plumber_text
            )
            
            result = {
                "success": True,
                "data": validated_data,
                "file_path": request.file_path,
                "request_id": request.request_id,
                "processing_info": {
                    "text_length": len(pdf_text),
                    "extraction_method": "enhanced_hybrid_async",
                    "confidence_score": validated_data["_metadata"]["confidence_score"],
                    "needs_human_review": validated_data["_metadata"]["confidence_score"] < 0.7
                }
            }
            
            # Cache the result
            await cache_manager.cache_result(file_hash, result)
            await cache_manager.set_request_status(request.request_id, "completed")
            
            return result
            
        except json.JSONDecodeError as e:
            await cache_manager.set_request_status(request.request_id, "failed")
            return {
                "success": False,
                "error": f"JSON decode error: {str(e)}",
                "request_id": request.request_id,
                "needs_human_review": True
            }
    
    except Exception as e:
        await cache_manager.set_request_status(request.request_id, "failed")
        logging.error(f"Processing error for request {request.request_id}: {e}")
        return {
            "success": False,
            "error": f"Processing error: {str(e)}",
            "request_id": request.request_id
        }

async def queue_processor():
    """Background task to process requests from queue"""
    while True:
        try:
            # Wait for request with timeout
            request = await asyncio.wait_for(request_queue.get(), timeout=1.0)
            
            # Acquire semaphore for concurrent processing limit
            await extraction_semaphore.acquire()
            
            # Create processing task
            task = asyncio.create_task(process_single_request(request))
            processing_tasks.add(task)
            
            # Add cleanup callback
            task.add_done_callback(lambda t: (
                processing_tasks.discard(t),
                extraction_semaphore.release()
            ))
            
        except asyncio.TimeoutError:
            # No requests in queue, continue
            continue
        except Exception as e:
            logging.error(f"Queue processor error: {e}")
            await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    """Initialize async resources"""
    global redis_pool, api_semaphore, extraction_semaphore, process_pool, session, cache_manager
    
    # Initialize Redis connection pool
    redis_pool = redis.Redis.from_url(
        "redis://localhost:6379", 
        encoding="utf-8", 
        decode_responses=True,
        max_connections=100
    )
    
    cache_manager = CacheManager(redis_pool)
    
    # Initialize semaphores for concurrency control
    api_semaphore = asyncio.Semaphore(config.api_rate_limit_per_minute)
    extraction_semaphore = asyncio.Semaphore(config.max_concurrent_extractions)
    
    # Initialize process pool for CPU-intensive tasks
    process_pool = ProcessPoolExecutor(max_workers=config.worker_processes)
    
    # Start background queue processor
    asyncio.create_task(queue_processor())
    
    logging.info("Scalable OCR service started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources"""
    global redis_pool, process_pool
    
    if redis_pool:
        await redis_pool.close()
    
    if process_pool:
        process_pool.shutdown(wait=True)
    
    # Cancel all processing tasks
    for task in processing_tasks:
        task.cancel()
    
    logging.info("Scalable OCR service shutdown")

@app.post("/process-insurance-certificate")
async def process_certificate_endpoint(
    file_path: str,
    priority: int = 1,
    background_tasks: BackgroundTasks = None
):
    """Async endpoint for processing insurance certificates"""
    
    # Check system health
    health = await ResourceManager.check_system_health()
    if not health["healthy"]:
        raise HTTPException(
            status_code=503,
            detail=f"System overloaded. Health: {health}"
        )
    
    # Check file size
    if os.path.exists(file_path):
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > config.max_file_size_mb:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {file_size_mb:.1f}MB (max: {config.max_file_size_mb}MB)"
            )
    
    # Generate request ID
    request_id = hashlib.md5(f"{file_path}_{datetime.now().isoformat()}".encode()).hexdigest()
    
    # Create processing request
    request = ProcessingRequest(
        request_id=request_id,
        file_path=file_path,
        priority=priority
    )
    
    # Add to queue
    try:
        await asyncio.wait_for(request_queue.put(request), timeout=5.0)
        await cache_manager.set_request_status(request_id, "queued")
        
        return {
            "success": True,
            "request_id": request_id,
            "status": "queued",
            "estimated_wait_minutes": request_queue.qsize() // 10  # Rough estimate
        }
        
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Request queue full. Please try again later."
        )

@app.get("/status/{request_id}")
async def get_processing_status(request_id: str):
    """Get processing status for a request"""
    status = await cache_manager.get_request_status(request_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # If completed, try to get cached result
    if status == "completed":
        # In a real implementation, you'd store the result reference
        return {"status": status, "message": "Processing completed. Check result endpoint."}
    
    return {"status": status}

@app.get("/health")
async def health_check():
    """System health endpoint"""
    return await ResourceManager.check_system_health()

if __name__ == "__main__":
    # Production-ready server configuration
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        workers=1,  # Single worker with async processing
        loop="uvloop",  # High-performance event loop
        access_log=False,  # Disable for performance
        log_level="info"
    ) 