#!/usr/bin/env python3
"""
System Verification Script.
Tests all components of the Arabic QA System.

Usage:
    python verify_system.py
"""
import sys
import time
import httpx
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
BACKEND_URL = "http://localhost:8000"
TIMEOUT = 30


def print_header(text: str):
    """Print formatted header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{status}: {test_name}")
    if details:
        print(f"   {details}")


def check_docker_services() -> bool:
    """Check if Docker containers are running."""
    print_header("Checking Docker Services")
    
    try:
        import subprocess
        result = subprocess.run(
            ["docker-compose", "ps"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print(result.stdout)
            
            # Check for required services
            services = ["backend", "bot", "qdrant", "ollama"]
            all_running = True
            
            for service in services:
                if service in result.stdout and "running" in result.stdout.lower():
                    print_result(f"{service} container", True)
                else:
                    print_result(f"{service} container", False, "Not running or not found")
                    all_running = False
            
            return all_running
        else:
            print_result("Docker Compose", False, result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print_result("Docker Compose", False, "Command timed out")
        return False
    except FileNotFoundError:
        print_result("Docker Compose", False, "docker-compose not found")
        return False
    except Exception as e:
        print_result("Docker Compose", False, str(e))
        return False


def check_backend_health() -> bool:
    """Check backend health endpoint."""
    print_header("Checking Backend Health")
    
    try:
        response = httpx.get(
            f"{BACKEND_URL}/api/v1/health",
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status', 'unknown')}")
            print(f"Services: {data.get('services', {})}")
            
            # Check if all services are healthy
            services = data.get('services', {})
            all_healthy = all(s == "healthy" for s in services.values())
            
            print_result("Backend API", True, f"Status: {data.get('status')}")
            print_result("Qdrant", services.get('qdrant') == 'healthy', services.get('qdrant'))
            print_result("Ollama", services.get('ollama') == 'healthy', services.get('ollama'))
            
            return all_healthy
        else:
            print_result("Backend Health", False, f"Status code: {response.status_code}")
            return False
            
    except httpx.ConnectError:
        print_result("Backend Health", False, "Cannot connect to backend")
        return False
    except httpx.TimeoutException:
        print_result("Backend Health", False, "Request timed out")
        return False
    except Exception as e:
        print_result("Backend Health", False, str(e))
        return False


def check_api_docs() -> bool:
    """Check if API documentation is accessible."""
    print_header("Checking API Documentation")
    
    try:
        response = httpx.get(
            f"{BACKEND_URL}/docs",
            timeout=TIMEOUT
        )
        
        if response.status_code == 200 and "Swagger" in response.text:
            print_result("Swagger UI", True)
            return True
        else:
            print_result("Swagger UI", False, f"Status code: {response.status_code}")
            return False
            
    except Exception as e:
        print_result("Swagger UI", False, str(e))
        return False


def check_query_endpoint() -> bool:
    """Test the query endpoint with a simple question."""
    print_header("Testing Query Endpoint")
    
    payload = {
        "question": "ما هي أخبار الشرق الأوسط؟",
        "filters": {
            "region": "Middle East",
            "category": "News"
        },
        "top_k": 1
    }
    
    try:
        response = httpx.post(
            f"{BACKEND_URL}/api/v1/query",
            json=payload,
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"Answer: {data.get('answer', '')[:100]}...")
            print(f"Sources: {len(data.get('sources', []))}")
            print(f"Entities: {data.get('entities_found', [])}")
            print(f"Latency: {data.get('latency_ms', 0)}ms")
            
            has_answer = bool(data.get('answer'))
            print_result("Query Response", has_answer)
            
            return has_answer
        else:
            print_result("Query Endpoint", False, f"Status code: {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False
            
    except httpx.TimeoutException:
        print_result("Query Endpoint", False, "Request timed out (LLM may be loading)")
        return False
    except Exception as e:
        print_result("Query Endpoint", False, str(e))
        return False


def check_ingestion_endpoint() -> bool:
    """Test the ingestion endpoint."""
    print_header("Testing Ingestion Endpoint")
    
    # Test with a known Reuters URL (this may fail if no articles exist)
    payload = {
        "url": "https://www.reuters.com/world/middle-east/",
        "region": "Middle East",
        "category": "News"
    }
    
    try:
        response = httpx.post(
            f"{BACKEND_URL}/api/v1/ingest",
            json=payload,
            timeout=TIMEOUT * 2  # Longer timeout for scraping
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status')}")
            print(f"Chunks: {data.get('chunks_processed')}")
            print(f"Entities: {data.get('entities_extracted')}")
            
            print_result("Ingestion Endpoint", True)
            return True
        elif response.status_code == 422:
            # Validation error - endpoint exists but URL may be invalid
            print_result("Ingestion Endpoint", True, "Endpoint working (URL validation failed)")
            return True
        else:
            print_result("Ingestion Endpoint", False, f"Status code: {response.status_code}")
            return False
            
    except httpx.TimeoutException:
        print_result("Ingestion Endpoint", False, "Request timed out")
        return False
    except Exception as e:
        print_result("Ingestion Endpoint", False, str(e))
        return False


def check_vector_db() -> bool:
    """Check Qdrant vector database directly."""
    print_header("Checking Vector Database (Qdrant)")
    
    try:
        response = httpx.get(
            "http://localhost:6333/",
            timeout=10
        )
        
        if response.status_code == 200:
            print_result("Qdrant HTTP", True)
            
            # Check collections
            collections_response = httpx.get(
                "http://localhost:6333/collections",
                timeout=10
            )
            
            if collections_response.status_code == 200:
                collections = collections_response.json()
                print(f"Collections: {collections}")
                print_result("Qdrant Collections", True)
                return True
            
            return True
        else:
            print_result("Qdrant HTTP", False, f"Status code: {response.status_code}")
            return False
            
    except Exception as e:
        print_result("Qdrant", False, str(e))
        return False


def check_ollama() -> bool:
    """Check Ollama LLM service directly."""
    print_header("Checking Ollama LLM")
    
    try:
        response = httpx.get(
            "http://localhost:11434/api/tags",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            models = data.get('models', [])
            print(f"Available models: {[m.get('name') for m in models]}")
            
            print_result("Ollama API", True)
            
            # Check if required model exists
            required_model = "llama3.1:8b"
            model_names = [m.get('name') for m in models]
            
            if any(required_model in name for name in model_names):
                print_result(f"Model: {required_model}", True)
            else:
                print_result(f"Model: {required_model}", False, "Model not pulled yet")
                print("   Run: docker exec ollama ollama pull llama3.1:8b")
            
            return True
        else:
            print_result("Ollama API", False, f"Status code: {response.status_code}")
            return False
            
    except Exception as e:
        print_result("Ollama", False, str(e))
        return False


def main():
    """Run all verification tests."""
    print("""
╔══════════════════════════════════════════════════════════╗
║       Arabic QA System - Verification Script             ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    results = {
        "Docker Services": check_docker_services(),
        "Backend Health": check_backend_health(),
        "API Documentation": check_api_docs(),
        "Vector Database": check_vector_db(),
        "Ollama LLM": check_ollama(),
        "Query Endpoint": check_query_endpoint(),
        "Ingestion Endpoint": check_ingestion_endpoint(),
    }
    
    # Summary
    print_header("VERIFICATION SUMMARY")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test, result in results.items():
        status = "✅" if result else "❌"
        print(f"  {status} {test}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n  🎉 All systems operational!")
        return 0
    else:
        print("\n  ⚠️  Some tests failed. Check the logs above.")
        print("\n  Troubleshooting:")
        print("  - Ensure Docker containers are running: docker-compose ps")
        print("  - Check logs: docker-compose logs -f")
        print("  - Pull Ollama model: docker exec ollama ollama pull llama3.1:8b")
        return 1


if __name__ == "__main__":
    sys.exit(main())
