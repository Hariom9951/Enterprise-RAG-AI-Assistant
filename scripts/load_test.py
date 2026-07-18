#!/usr/bin/env python3
"""
Enterprise RAG AI Assistant — Asynchronous HTTP Load Test Benchmark
==================================================================
Benchmarks concurrent requests against health endpoints and calculates
latency percentiles (P50, P90, P95, P99) and success rate.

Usage:
    python scripts/load_test.py --url http://localhost:8000/api/v1/health --concurrency 50 --requests 500
"""

import argparse
import asyncio
import time
import sys
from typing import List

# Ensure httpx is available
try:
    import httpx
except ImportError:
    print("Error: 'httpx' is required for this load test script. Please run 'pip install httpx'.")
    sys.exit(1)


class BenchmarkRunner:
    def __init__(self, target_url: str, concurrency: int, total_requests: int):
        self.target_url = target_url
        self.concurrency = concurrency
        self.total_requests = total_requests
        self.latencies: List[float] = []
        self.success_count = 0
        self.failure_count = 0

    async def _send_request(self, client: httpx.AsyncClient):
        start_time = time.perf_counter()
        try:
            resp = await client.get(self.target_url, timeout=10.0)
            elapsed = (time.perf_counter() - start_time) * 1000  # in ms
            if resp.status_code == 200:
                self.success_count += 1
                self.latencies.append(elapsed)
            else:
                self.failure_count += 1
        except Exception:
            self.failure_count += 1

    async def run(self):
        sem = asyncio.Semaphore(self.concurrency)
        
        async with httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=self.concurrency)) as client:
            async def worker():
                while True:
                    # Limit overall request count
                    current_count = self.success_count + self.failure_count
                    if current_count >= self.total_requests:
                        break
                    
                    async with sem:
                        await self._send_request(client)

            # Start workers
            workers = [asyncio.create_task(worker()) for _ in range(self.concurrency)]
            await asyncio.gather(*workers)

    def print_report(self, duration: float):
        total = self.success_count + self.failure_count
        if not total:
            print("Error: No requests were sent.")
            return

        success_rate = (self.success_count / total) * 100
        qps = total / duration

        print("=" * 60)
        print("          HTTP BENCHMARK REPORT          ")
        print("=" * 60)
        print(f"Target URL:          {self.target_url}")
        print(f"Concurrency Limit:   {self.concurrency}")
        print(f"Total Requests:      {total}")
        print(f"Success Rate:        {success_rate:.2f}% (Success: {self.success_count}, Fail: {self.failure_count})")
        print(f"Test Duration:       {duration:.2f} seconds")
        print(f"Requests / Second:   {qps:.2f} QPS")
        print("-" * 60)
        
        if self.latencies:
            self.latencies.sort()
            avg_lat = sum(self.latencies) / len(self.latencies)
            min_lat = self.latencies[0]
            max_lat = self.latencies[-1]
            p50 = self.latencies[int(len(self.latencies) * 0.50)]
            p90 = self.latencies[int(len(self.latencies) * 0.90)]
            p95 = self.latencies[int(len(self.latencies) * 0.95)]
            p99 = self.latencies[int(len(self.latencies) * 0.99)]

            print("Latency Statistics (ms):")
            print(f"  Minimum:           {min_lat:.2f} ms")
            print(f"  Average:           {avg_lat:.2f} ms")
            print(f"  P50 (Median):       {p50:.2f} ms")
            print(f"  P90:               {p90:.2f} ms")
            print(f"  P95:               {p95:.2f} ms")
            print(f"  P99:               {p99:.2f} ms")
            print(f"  Maximum:           {max_lat:.2f} ms")
        else:
            print("Error: No successful latency records available.")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Concurrent HTTP load test benchmark.")
    parser.add_argument("--url", default="http://localhost:8000/api/v1/health", help="Target URL to query.")
    parser.add_argument("--concurrency", type=int, default=30, help="Number of concurrent worker tasks.")
    parser.add_argument("--requests", type=int, default=200, help="Total number of HTTP requests to make.")
    args = parser.parse_args()

    print(f"[Benchmark] Warming up and checking target: {args.url}...")
    
    start_time = time.perf_counter()
    runner = BenchmarkRunner(args.url, args.concurrency, args.requests)
    asyncio.run(runner.run())
    duration = time.perf_counter() - start_time
    
    runner.print_report(duration)


if __name__ == "__main__":
    main()
