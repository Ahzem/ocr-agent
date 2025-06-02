#!/usr/bin/env python3
"""
Load Testing Script for Scalable OCR System
Usage: locust -f load_test.py --host=http://localhost
"""

from locust import HttpUser, task, between, events
import json
import random
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OCRUser(HttpUser):
    wait_time = between(1, 5)  # Wait 1-5 seconds between requests
    
    def on_start(self):
        """Called when a user starts"""
        # Test files to simulate different PDFs
        self.test_files = [
            "/docs/test1.pdf",
            "/docs/test2.pdf", 
            "/docs/test3.pdf",
            "/docs/sample.pdf",
            "/docs/insurance_cert.pdf"
        ]
        
        # Track request IDs for status checking
        self.pending_requests = []
        
        logger.info(f"User {self.environment.runner.user_count} started")
    
    @task(5)
    def process_certificate(self):
        """Main task: Process insurance certificate"""
        file_path = random.choice(self.test_files)
        priority = random.choice([1, 1, 1, 2, 3])  # Mostly normal priority
        
        payload = {
            "file_path": file_path,
            "priority": priority
        }
        
        with self.client.post(
            "/process-insurance-certificate",
            json=payload,
            catch_response=True,
            name="process_certificate"
        ) as response:
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "request_id" in data and data.get("success"):
                        response.success()
                        self.pending_requests.append({
                            "request_id": data["request_id"],
                            "submitted_at": time.time()
                        })
                        logger.debug(f"Submitted request: {data['request_id']}")
                    else:
                        response.failure(f"Invalid response: {data}")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            elif response.status_code == 503:
                # Service overloaded - expected under high load
                response.success()
                logger.info("Service overloaded - queue full")
            else:
                response.failure(f"HTTP {response.status_code}")
    
    @task(3)
    def check_status(self):
        """Check status of pending requests"""
        if not self.pending_requests:
            return
        
        # Check oldest pending request
        request_info = self.pending_requests[0]
        request_id = request_info["request_id"]
        
        with self.client.get(
            f"/status/{request_id}",
            catch_response=True,
            name="check_status"
        ) as response:
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    status = data.get("status", "unknown")
                    
                    if status == "completed":
                        # Remove from pending list
                        self.pending_requests.pop(0)
                        processing_time = time.time() - request_info["submitted_at"]
                        logger.info(f"Request {request_id} completed in {processing_time:.2f}s")
                        response.success()
                    elif status in ["processing", "queued"]:
                        response.success()
                    elif status == "failed":
                        self.pending_requests.pop(0)
                        response.failure(f"Request failed: {data}")
                    else:
                        response.success()
                        
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            elif response.status_code == 404:
                # Request not found - remove from pending
                self.pending_requests.pop(0)
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")
    
    @task(1)
    def health_check(self):
        """Check system health"""
        with self.client.get(
            "/health",
            catch_response=True,
            name="health_check"
        ) as response:
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("healthy", False):
                        response.success()
                    else:
                        response.failure(f"System unhealthy: {data}")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"HTTP {response.status_code}")

class HighPriorityUser(HttpUser):
    """Simulates high-priority users (e.g., VIP clients)"""
    wait_time = between(2, 8)
    weight = 1  # 1 high-priority user for every 10 regular users
    
    def on_start(self):
        self.test_files = ["/docs/vip_test.pdf"]
        self.pending_requests = []
    
    @task(10)
    def process_high_priority_certificate(self):
        """Process with high priority"""
        payload = {
            "file_path": random.choice(self.test_files),
            "priority": 1  # High priority
        }
        
        with self.client.post(
            "/process-insurance-certificate",
            json=payload,
            catch_response=True,
            name="process_high_priority"
        ) as response:
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "request_id" in data:
                        response.success()
                        self.pending_requests.append({
                            "request_id": data["request_id"],
                            "submitted_at": time.time()
                        })
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"HTTP {response.status_code}")

# Locust event handlers for detailed reporting
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, context, **kwargs):
    """Log detailed request information"""
    if exception:
        logger.error(f"{request_type} {name} failed: {exception}")
    elif response_time > 5000:  # Log slow requests (>5s)
        logger.warning(f"Slow request: {request_type} {name} took {response_time:.0f}ms")

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts"""
    logger.info("🚀 Load test starting...")
    logger.info(f"Target host: {environment.host}")

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops"""
    logger.info("🏁 Load test completed")
    
    # Print summary statistics
    stats = environment.stats
    logger.info(f"Total requests: {stats.total.num_requests}")
    logger.info(f"Failures: {stats.total.num_failures}")
    logger.info(f"Average response time: {stats.total.avg_response_time:.2f}ms")
    logger.info(f"95th percentile: {stats.total.get_response_time_percentile(0.95):.2f}ms")

# Custom test scenarios
class StressTestUser(HttpUser):
    """Stress test user that pushes system limits"""
    wait_time = between(0.1, 0.5)  # Very aggressive
    weight = 0  # Only used in stress tests
    
    @task
    def rapid_fire_requests(self):
        """Send requests as fast as possible"""
        payload = {"file_path": "/docs/stress_test.pdf", "priority": 3}
        
        self.client.post(
            "/process-insurance-certificate",
            json=payload,
            name="stress_test"
        )

if __name__ == "__main__":
    print("""
    Load Testing Script for Scalable OCR System
    
    Usage Examples:
    
    1. Basic Load Test (50 users):
       locust -f load_test.py --host=http://localhost -u 50 -r 5 -t 5m --headless
    
    2. Gradual Ramp-up Test:
       locust -f load_test.py --host=http://localhost -u 200 -r 10 -t 10m --headless
    
    3. Stress Test:
       locust -f load_test.py --host=http://localhost -u 500 -r 50 -t 3m --headless
    
    4. Interactive Mode:
       locust -f load_test.py --host=http://localhost
       # Then open http://localhost:8089
    
    Key Metrics to Monitor:
    - Response time percentiles (50th, 95th, 99th)
    - Request failure rate
    - System health during load
    - Queue size growth
    - Memory usage
    """) 