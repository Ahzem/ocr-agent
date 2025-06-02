"""
Test script to demonstrate the Insurance Certificate OCR API
"""
import requests
import json

# API base URL (adjust if running on different port)
BASE_URL = "http://localhost:8000"

def test_api():
    """Test the API endpoints"""
    
    print("🧪 Testing Insurance Certificate OCR API\n")
    
    # Test 1: Health check
    print("1. Testing health check...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"✅ Health check: {response.json()}")
    except Exception as e:
        print(f"❌ Health check failed: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 2: Process from URL
    print("2. Testing PDF processing from URL...")
    test_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
    
    try:
        payload = {"file_path": test_url}
        response = requests.post(f"{BASE_URL}/process", json=payload)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Processing successful!")
            print(f"📄 File: {result['file_path']}")
            print(f"📊 Processing info: {result.get('processing_info', {})}")
            print("📋 Extracted data:")
            print(json.dumps(result['data'], indent=2))
        else:
            print(f"❌ Processing failed: {response.status_code}")
            print(response.json())
            
    except Exception as e:
        print(f"❌ URL processing test failed: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 3: Process with URL-specific endpoint
    print("3. Testing URL-specific endpoint...")
    try:
        payload = {"url": test_url}
        response = requests.post(f"{BASE_URL}/process-url", json=payload)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ URL processing successful!")
            print(f"🔗 URL: {result['url']}")
        else:
            print(f"❌ URL processing failed: {response.status_code}")
            print(response.json())
            
    except Exception as e:
        print(f"❌ URL-specific test failed: {e}")

def test_with_your_pdf():
    """Test with your own PDF URL"""
    
    print("\n" + "="*60)
    print("🔧 CUSTOM TEST - Replace with your PDF URL")
    print("="*60)
    
    # Replace this with your actual PDF URL
    your_pdf_url = "https://example.com/your-certificate.pdf"
    
    payload = {"file_path": your_pdf_url}
    
    try:
        response = requests.post(f"{BASE_URL}/process", json=payload)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Your PDF processed successfully!")
            print(json.dumps(result, indent=2))
        else:
            print(f"❌ Failed to process your PDF: {response.status_code}")
            print(response.json())
            
    except Exception as e:
        print(f"❌ Custom test failed: {e}")

if __name__ == "__main__":
    print("Starting API tests...")
    print("Make sure the FastAPI server is running on http://localhost:8000")
    print("Run: uvicorn main:app --reload --port 8000\n")
    
    # Run basic tests
    test_api()
    
    # Uncomment and modify the line below to test with your PDF
    # test_with_your_pdf()
    
    print("\n🏁 Testing complete!") 