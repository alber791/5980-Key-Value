"""
Benchmark for distributed KV store with consistent hashing.
Measures throughput and latency across 1, 2, and 3 instances.
"""

import threading
import requests
import time
import json
from typing import List, Dict
import matplotlib.pyplot as plt

# Configuration
BASE_URL = 'http://127.0.0.1:8080'  # Router endpoint
NUM_THREADS = 10
OPS_PER_THREAD = 100
KEYSPACE_SIZE = 300

STORES = [
    "http://kv_store_1:8080",
    "http://kv_store_2:8080",
    "http://kv_store_3:8080",
]


def kv_store_operation(op_type: str, key: str, value=None) -> bool:
    """Execute a single KV store operation."""
    try:
        if op_type == 'set':
            response = requests.post(f"{BASE_URL}/{key}", json={'value': value}, timeout=10)
        elif op_type == 'get':
            response = requests.get(f"{BASE_URL}/{key}", timeout=10)
        else:
            raise ValueError("Invalid operation type")
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error during {op_type} operation for key '{key}': {e}")
        return False


def configure_router_store_count(count: int) -> None:
    stores = STORES[:count]
    response = requests.post(f"{BASE_URL}/admin/stores", json={"stores": stores}, timeout=10)
    response.raise_for_status()
    payload = response.json()
    print(f"[INFO] Router configured with {payload['store_count']} store(s): {payload['stores']}")


def prepopulate_keys() -> None:
    for i in range(KEYSPACE_SIZE):
        key = f"seed_key_{i}"
        value = f"seed_value_{i}"
        ok = kv_store_operation("set", key, value)
        if not ok:
            raise RuntimeError("Failed to prepopulate keys before benchmark")


def worker_thread(start_event: threading.Event, operations: List[tuple], latencies: List[float], lock: threading.Lock):
    """Worker thread that processes a slice of operations and records successful call latency."""
    start_event.wait()
    local_latencies: List[float] = []
    for op, key, value in operations:
        start_time = time.time()
        if kv_store_operation(op, key, value):
            local_latencies.append(time.time() - start_time)

    with lock:
        latencies.extend(local_latencies)


def run_benchmark(test_name: str) -> Dict[str, float]:
    """Run a single benchmark test and return results."""
    print(f"\n{'='*60}")
    print(f"Running benchmark: {test_name}")
    print(f"{'='*60}")
    
    total_ops = NUM_THREADS * OPS_PER_THREAD
    operations: List[tuple] = []
    for i in range(total_ops):
        key_index = i % KEYSPACE_SIZE
        key = f"seed_key_{key_index}"
        if i % 2 == 0:
            operations.append(("get", key, None))
        else:
            operations.append(("set", key, f"updated_value_{i}"))

    ops_per_thread = len(operations) // NUM_THREADS
    thread_batches: List[List[tuple]] = []
    start = 0
    for thread_idx in range(NUM_THREADS):
        end = start + ops_per_thread
        if thread_idx == NUM_THREADS - 1:
            end = len(operations)
        thread_batches.append(operations[start:end])
        start = end

    start_event = threading.Event()
    latencies: List[float] = []
    latencies_lock = threading.Lock()
    threads = [
        threading.Thread(
            target=worker_thread,
            args=(start_event, thread_batches[i], latencies, latencies_lock),
        )
        for i in range(NUM_THREADS)
    ]

    start_time = time.time()
    for thread in threads:
        thread.start()

    start_event.set()

    for thread in threads:
        thread.join()

    total_time = time.time() - start_time
    average_latency = sum(latencies) / len(latencies) if latencies else 0.0
    throughput = len(latencies) / total_time if total_time > 0 else 0.0
    
    results = {
        'test_name': test_name,
        'total_ops': len(latencies),
        'total_time': total_time,
        'throughput': throughput,
        'avg_latency': average_latency,
        'min_latency': min(latencies) if latencies else 0.0,
        'max_latency': max(latencies) if latencies else 0.0,
    }
    
    print("\nFinal Results:")
    print(f"Total operations: {results['total_ops']}")
    print(f"Total time: {results['total_time']:.2f} seconds")
    print(f"Throughput: {results['throughput']:.2f} operations per second")
    print(f"Average Latency: {results['avg_latency']*1000:.2f} ms")
    print(f"Min Latency: {results['min_latency']*1000:.2f} ms")
    print(f"Max Latency: {results['max_latency']*1000:.2f} ms")
    
    return results


def plot_results(all_results: List[Dict]):
    """Generate comparison plots for all test runs."""
    test_names = [r['test_name'] for r in all_results]
    throughputs = [r['throughput'] for r in all_results]
    avg_latencies = [r['avg_latency'] * 1000 for r in all_results]  # Convert to ms
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    
    # Throughput comparison
    ax1.bar(test_names, throughputs, color=['#FF6B6B', '#4ECDC4', '#45B7D1'])
    ax1.set_ylabel('Throughput (ops/sec)', fontsize=12)
    ax1.set_title('Throughput Comparison', fontsize=14, fontweight='bold')
    ax1.grid(axis='y', alpha=0.3)
    for i, v in enumerate(throughputs):
        ax1.text(i, v + 1, f'{v:.2f}', ha='center', va='bottom')
    
    # Latency comparison
    ax2.bar(test_names, avg_latencies, color=['#FF6B6B', '#4ECDC4', '#45B7D1'])
    ax2.set_ylabel('Average Latency (ms)', fontsize=12)
    ax2.set_title('Latency Comparison', fontsize=14, fontweight='bold')
    ax2.grid(axis='y', alpha=0.3)
    for i, v in enumerate(avg_latencies):
        ax2.text(i, v + 0.5, f'{v:.2f}', ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig('performance_comparison.png', dpi=300, bbox_inches='tight')
    print("\n[INFO] Performance comparison chart saved to 'performance_comparison.png'")
    plt.close()


def main():
    """Run benchmarks for 1, 2, and 3 KV store configurations."""
    print("\n" + "="*60)
    print("Distributed KV Store Benchmark")
    print("="*60)
    
    all_results = []

    try:
        requests.get(f"{BASE_URL}/health", timeout=5).raise_for_status()
    except Exception as exc:
        print("[ERROR] Router is not reachable at http://127.0.0.1:8080")
        print("[ERROR] Start docker compose first, then rerun benchmark.")
        raise SystemExit(1) from exc

    prepopulate_keys()

    for count in [1, 2, 3]:
        configure_router_store_count(count)
        time.sleep(1)
        result = run_benchmark(f"{count} KV Store" if count == 1 else f"{count} KV Stores")
        all_results.append(result)
    
    # Summary report
    print("\n" + "="*60)
    print("PERFORMANCE SUMMARY")
    print("="*60)
    print(f"{'Configuration':<20} {'Throughput (ops/s)':<20} {'Latency (ms)':<20}")
    print("-"*60)
    for result in all_results:
        print(f"{result['test_name']:<20} {result['throughput']:<20.2f} {result['avg_latency']*1000:<20.2f}")
    
    # Calculate improvements
    baseline_throughput = all_results[0]['throughput']
    baseline_latency = all_results[0]['avg_latency']
    
    print("\n" + "-"*60)
    print("PERFORMANCE DELTA (relative to 1 KV Store)")
    print("-"*60)
    for i, result in enumerate(all_results):
        if i > 0:
            throughput_delta = ((result['throughput'] - baseline_throughput) / baseline_throughput) * 100
            latency_delta = ((result['avg_latency'] - baseline_latency) / baseline_latency) * 100
            print(f"{result['test_name']:<20} Throughput: {throughput_delta:+.2f}% | "
                  f"Latency: {latency_delta:+.2f}%")
    
    # Save results to JSON
    with open('benchmark_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    print("\n[INFO] Results saved to 'benchmark_results.json'")
    
    # Generate plots
    plot_results(all_results)
    
    print("\n" + "="*60)
    print("Benchmark complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()