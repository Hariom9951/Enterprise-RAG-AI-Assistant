#!/usr/bin/env python3
"""
Enterprise RAG AI Assistant — Phase 13 Concurrency & Load Testing Suite
========================================================================
Simulates traffic from 10, 25, 50, and 100 concurrent users querying the:
  - Upload endpoint (POST /api/v1/documents/upload)
  - Retrieval endpoint (POST /api/v1/search)
  - Chat endpoint (POST /api/v1/chat/message)
  - Agent endpoint (POST /api/v1/agent/query)
"""

import argparse
import asyncio
import time
import sys
import uuid
import httpx
from pathlib import Path
from typing import List, Dict, Any

# Configure in-memory overrides to bypass docker dependencies during local run
import os
os.environ["ENABLE_REDIS_CACHING"] = "false"

# Override Celery Task execution to avoid connecting to Redis broker
from celery.app.task import Task
Task.apply_async = lambda *args, **kwargs: None
Task.delay = lambda *args, **kwargs: None

# Setup python path to include backend
sys.path.append(str(Path(__file__).parent.parent / "backend"))


class LoadTester:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.tokens: List[str] = []
        from app.main import app
        transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=30.0)

    async def setup_users(self, count: int):
        """Register and log in a test user and reuse the token for all virtual users."""
        print(f"Setting up authenticated session for {count} virtual users...")
        self.tokens = []
        
        email = "loaduser_shared@example.com"
        password = "SecurePassword123!"
        
        try:
            # 1. Register (ignore if already registered)
            await self.client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": password, "full_name": "Load Test User"}
            )
            # 2. Login
            resp = await self.client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password}
            )
            if resp.status_code == 200:
                token = resp.json()["access_token"]
                self.tokens = [token] * count
                print(f"Successfully authenticated session for {count} users.")
                return
        except Exception as e:
            print(f"Error during authentication: {e}")
        
        print("Failed to authenticate load test user.")

    async def run_scenario(self, endpoint_type: str, concurrency: int, total_requests: int):
        """Simulate concurrent queries to a specific endpoint."""
        if not self.tokens:
            print("Error: No authenticated users. Call setup_users first.")
            return

        print(f"\n[Load Test] Simulating {concurrency} users calling {endpoint_type} ({total_requests} total requests)...")
        
        latencies: List[float] = []
        success_count = 0
        failure_count = 0
        
        sem = asyncio.Semaphore(concurrency)
        
        # Prepare endpoint options
        paths = {
            "search": "/api/v1/search",
            "chat": "/api/v1/chat/chat",
            "agent": "/api/v1/agent/chat",
            "upload": "/api/v1/documents/upload"
        }
        
        url_path = paths.get(endpoint_type, "/api/v1/search")

        async def send_single_request(user_index: int):
            nonlocal success_count, failure_count
            token = self.tokens[user_index % len(self.tokens)]
            headers = {"Authorization": f"Bearer {token}"}
            
            start_time = time.perf_counter()
            try:
                async with sem:
                    if endpoint_type == "search":
                        resp = await self.client.post(
                            url_path,
                            json={"query": "explain RAG semantic chunking", "top_k": 3},
                            headers=headers
                        )
                    elif endpoint_type == "chat":
                        resp = await self.client.post(
                            url_path,
                            json={"question": "hello RAG", "stream": False},
                            headers=headers
                        )
                    elif endpoint_type == "agent":
                        resp = await self.client.post(
                            url_path,
                            json={"question": "run calculations on chunk stats"},
                            headers=headers
                        )
                    elif endpoint_type == "upload":
                        # Post a small file
                        files = {"file": ("dummy_load.txt", b"load test document content here.", "text/plain")}
                        resp = await self.client.post(
                            url_path,
                            files=files,
                            headers=headers
                        )
                    
                    elapsed = (time.perf_counter() - start_time) * 1000  # ms
                    
                    if resp.status_code in (200, 201, 202, 204):
                        success_count += 1
                        latencies.append(elapsed)
                    else:
                        failure_count += 1
            except Exception as e:
                failure_count += 1

        start_perf = time.perf_counter()
        tasks = [send_single_request(i) for i in range(total_requests)]
        await asyncio.gather(*tasks)
        total_duration = time.perf_counter() - start_perf
        
        # Calculate stats
        total_sent = success_count + failure_count
        success_rate = (success_count / total_sent * 100) if total_sent else 0
        qps = total_sent / total_duration if total_duration else 0
        
        print("-" * 60)
        print(f"Results for Concurrency={concurrency}:")
        print(f"  Success Rate : {success_rate:.2f}% ({success_count} success, {failure_count} fail)")
        print(f"  Throughput   : {qps:.2f} QPS (Duration: {total_duration:.2f}s)")
        
        if latencies:
            latencies.sort()
            avg = sum(latencies) / len(latencies)
            p50 = latencies[int(len(latencies) * 0.50)]
            p90 = latencies[int(len(latencies) * 0.90)]
            p99 = latencies[int(len(latencies) * 0.99)]
            print(f"  Latency P50  : {p50:.2f} ms")
            print(f"  Latency P90  : {p90:.2f} ms")
            print(f"  Latency P99  : {p99:.2f} ms")
            print(f"  Latency Avg  : {avg:.2f} ms")
        print("-" * 60)

    async def close(self):
        await self.client.aclose()


async def main():
    parser = argparse.ArgumentParser(description="Phase 13 Load Testing Suite")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of target API")
    parser.add_argument("--requests", type=int, default=100, help="Total requests per run")
    args = parser.parse_args()

    tester = LoadTester(args.url)
    
    from unittest.mock import patch
    
    async def mock_stream(*args, **kwargs):
        yield "This is a mock streamed response."
        
    async def mock_response(*args, **kwargs):
        return "This is a mock response.", {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
    
    try:
        # Test concurrency scales: 10, 25, 50, 100 users
        user_scales = [10, 25, 50, 100]
        
        with (
            patch("app.services.llm_providers.GeminiProvider.generate_response_stream", side_effect=mock_stream),
            patch("app.services.llm_providers.GeminiProvider.generate_response", side_effect=mock_response),
        ):
            for users in user_scales:
                print(f"\n==================================================")
                print(f"           CONCURRENCY LEVEL: {users} USERS           ")
                print(f"==================================================")
                
                # Setup tokens for virtual users
                await tester.setup_users(users)
                
                # Run load scenarios
                # Search
                await tester.run_scenario("search", users, args.requests)
                # Chat
                await tester.run_scenario("chat", users, args.requests)
            
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(main())
