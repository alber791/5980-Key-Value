"""
Benchmark for distributed KV store with consistent hashing.
Measures throughput and latency across 1, 2, and 3 instances.
"""

import bisect
import hashlib
import threading
import requests
import time
import json
from typing import List, Dict, Optional, Tuple
import matplotlib.pyplot as plt

# Configuration
STORE_URLS = [
    "http://127.0.0.1:8081",
    "http://127.0.0.1:8082",
    "http://127.0.0.1:8083",
]
NUM_THREADS = 40
OPS_PER_THREAD = 150
KEYSPACE_SIZE = 1000
WARMUP_REQUESTS = 200
VIRTUAL_NODES = 128


class ConsistentHashRing:
    def __init__(self, nodes: List[str], replicas: int = VIRTUAL_NODES):
        if not nodes:
            raise ValueError("At least one node is required")
        self.nodes = nodes
        self.replicas = replicas
        self.positions: List[int] = []
        self.node_map: Dict[int, str] = {}

        for node in nodes:
            for replica in range(replicas):
                digest = hashlib.md5(f"{node}:{replica}".encode("utf-8")).hexdigest()
                position = int(digest, 16)
                self.positions.append(position)
                self.node_map[position] = node

        self.positions.sort()

    def get_node(self, key: str) -> str:
        digest = hashlib.md5(key.encode("utf-8")).hexdigest()
        key_position = int(digest, 16)
        index = bisect.bisect(self.positions, key_position)
        if index == len(self.positions):
            index = 0
        return self.node_map[self.positions[index]]


def build_ring(store_count: int) -> ConsistentHashRing:
    return ConsistentHashRing(STORE_URLS[:store_count])


def kv_store_operation(
    session: requests.Session,
    ring: ConsistentHashRing,
    op_type: str,
    key: str,
    value=None,
) -> bool:
    """Execute a single KV store operation."""
    base_url = ring.get_node(key)
    try:
        if op_type == "set":
            response = session.post(f"{base_url}/{key}", json={"value": value}, timeout=10)
        elif op_type == "get":
            response = session.get(f"{base_url}/{key}", timeout=10)
        elif op_type == "delete":
            response = session.delete(f"{base_url}/{key}", timeout=10)
        else:
            raise ValueError("Invalid operation type")
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error during {op_type} operation for key '{key}' on {base_url}: {e}")
        return False


def reset_cluster_data() -> None:
    with requests.Session() as session:
        for store_url in STORE_URLS:
            response = session.post(f"{store_url}/admin/reset", timeout=10)
            response.raise_for_status()


def prepopulate_keys(ring: ConsistentHashRing) -> None:
    with requests.Session() as session:
        for i in range(KEYSPACE_SIZE):
            key = f"seed_key_{i}"
            value = f"seed_value_{i}"
            ok = kv_store_operation(session, ring, "set", key, value)
            if not ok:
                raise RuntimeError("Failed to prepopulate keys before benchmark")


def warmup_cluster(ring: ConsistentHashRing) -> None:
    with requests.Session() as session:
        for i in range(WARMUP_REQUESTS):
            key = f"seed_key_{i % KEYSPACE_SIZE}"
            kv_store_operation(session, ring, "get", key)


def build_thread_batches() -> List[List[Tuple[str, str, Optional[str]]]]:
    batches: List[List[Tuple[str, str, Optional[str]]]] = []
    for thread_idx in range(NUM_THREADS):
        batch: List[Tuple[str, str, Optional[str]]] = []
        for op_idx in range(OPS_PER_THREAD):
            seed_index = (thread_idx * OPS_PER_THREAD + op_idx) % KEYSPACE_SIZE
            temp_key = f"temp_key_{thread_idx}_{op_idx // 4}"
            phase = op_idx % 4

            if phase == 0:
                batch.append(("get", f"seed_key_{seed_index}", None))
            elif phase == 1:
                batch.append(("set", f"seed_key_{seed_index}", f"updated_value_{thread_idx}_{op_idx}"))
            elif phase == 2:
                batch.append(("set", temp_key, f"temp_value_{thread_idx}_{op_idx}"))
            else:
                batch.append(("delete", temp_key, None))
        batches.append(batch)
    return batches


def worker_thread(
    start_event: threading.Event,
    ring: ConsistentHashRing,
    operations: List[Tuple[str, str, Optional[str]]],
    latencies: List[float],
    outcomes: List[bool],
    lock: threading.Lock,
):
    """Worker thread that processes a slice of operations and records latency and success."""
    session = requests.Session()
    session.headers.update({"Connection": "keep-alive"})
    adapter = requests.adapters.HTTPAdapter(pool_connections=256, pool_maxsize=256)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    start_event.wait()
    local_latencies: List[float] = []
    local_outcomes: List[bool] = []
    for op, key, value in operations:
        start_time = time.perf_counter()
        ok = kv_store_operation(session, ring, op, key, value)
        local_latencies.append(time.perf_counter() - start_time)
        local_outcomes.append(ok)

    session.close()

    with lock:
        latencies.extend(local_latencies)
        outcomes.extend(local_outcomes)


def run_benchmark(test_name: str, ring: ConsistentHashRing) -> Dict[str, float]:
    """Run a single benchmark test and return results."""
    print(f"\n{'='*60}")
    print(f"Running benchmark: {test_name}")
    print(f"{'='*60}")

    thread_batches = build_thread_batches()
    total_ops = sum(len(batch) for batch in thread_batches)

    start_event = threading.Event()
    latencies: List[float] = []
    outcomes: List[bool] = []
    latencies_lock = threading.Lock()
    threads = [
        threading.Thread(
            target=worker_thread,
            args=(start_event, ring, thread_batches[i], latencies, outcomes, latencies_lock),
        )
        for i in range(NUM_THREADS)
    ]

    start_time = time.perf_counter()
    for thread in threads:
        thread.start()

    start_event.set()

    for thread in threads:
        thread.join()

    total_time = time.perf_counter() - start_time
    successful_ops = sum(outcomes)
    failed_ops = len(outcomes) - successful_ops
    error_rate = (failed_ops / len(outcomes) * 100) if outcomes else 0.0
    average_latency = sum(latencies) / len(latencies) if latencies else 0.0
    throughput = successful_ops / total_time if total_time > 0 else 0.0

    results = {
        "test_name": test_name,
        "total_ops": total_ops,
        "successful_ops": successful_ops,
        "failed_ops": failed_ops,
        "total_time": total_time,
        "throughput": throughput,
        "avg_latency": average_latency,
        "min_latency": min(latencies) if latencies else 0.0,
        "max_latency": max(latencies) if latencies else 0.0,
        "error_rate": error_rate,
    }

    print("\nFinal Results:")
    print(f"Total operations: {results['total_ops']}")
    print(f"Successful operations: {results['successful_ops']}")
    print(f"Failed operations: {results['failed_ops']}")
    print(f"Total time: {results['total_time']:.2f} seconds")
    print(f"Throughput: {results['throughput']:.2f} operations per second")
    print(f"Average Latency: {results['avg_latency']*1000:.2f} ms")
    print(f"Min Latency: {results['min_latency']*1000:.2f} ms")
    print(f"Max Latency: {results['max_latency']*1000:.2f} ms")
    print(f"Error Rate: {results['error_rate']:.2f}%")

    return results


def plot_results(all_results: List[Dict]):
    """Generate comparison plots for all test runs."""
    test_names = [r["test_name"] for r in all_results]
    throughputs = [r["throughput"] for r in all_results]
    avg_latencies = [r["avg_latency"] * 1000 for r in all_results]  # Convert to ms
    error_rates = [r["error_rate"] for r in all_results]

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(18, 5))

    ax1.bar(test_names, throughputs, color=["#FF6B6B", "#4ECDC4", "#45B7D1"])
    ax1.set_ylabel("Throughput (ops/sec)", fontsize=12)
    ax1.set_title("Throughput Comparison", fontsize=14, fontweight="bold")
    ax1.grid(axis="y", alpha=0.3)
    for i, v in enumerate(throughputs):
        ax1.text(i, v + 1, f"{v:.2f}", ha="center", va="bottom")

    ax2.bar(test_names, avg_latencies, color=["#FF6B6B", "#4ECDC4", "#45B7D1"])
    ax2.set_ylabel("Average Latency (ms)", fontsize=12)
    ax2.set_title("Latency Comparison", fontsize=14, fontweight="bold")
    ax2.grid(axis="y", alpha=0.3)
    for i, v in enumerate(avg_latencies):
        ax2.text(i, v + 0.5, f"{v:.2f}", ha="center", va="bottom")

    ax3.bar(test_names, error_rates, color=["#FFA726", "#AB47BC", "#66BB6A"])
    ax3.set_ylabel("Error Rate (%)", fontsize=12)
    ax3.set_title("Error Rate Comparison", fontsize=14, fontweight="bold")
    ax3.grid(axis="y", alpha=0.3)
    for i, v in enumerate(error_rates):
        ax3.text(i, v + 0.1, f"{v:.2f}%", ha="center", va="bottom")

    plt.tight_layout()
    plt.savefig("performance_comparison.png", dpi=300, bbox_inches="tight")
    print("\n[INFO] Performance comparison chart saved to 'performance_comparison.png'")
    plt.close()


def main():
    """Run benchmarks for 1, 2, and 3 KV store configurations."""
    print("\n" + "=" * 60)
    print("Distributed KV Store Benchmark")
    print("=" * 60)

    all_results = []

    for count in [1, 2, 3]:
        ring = build_ring(count)
        try:
            with requests.Session() as session:
                for store_url in STORE_URLS[:count]:
                    session.get(f"{store_url}/admin/dump", timeout=5).raise_for_status()
        except Exception as exc:
            print("[ERROR] One or more KV stores are not reachable on localhost ports 8081-8083")
            print("[ERROR] Start docker compose first, then rerun benchmark.")
            raise SystemExit(1) from exc

        print(f"[INFO] Benchmarking direct client-side hashing across {count} store(s): {STORE_URLS[:count]}")
        reset_cluster_data()
        prepopulate_keys(ring)
        warmup_cluster(ring)
        time.sleep(1)
        result = run_benchmark(
            f"{count} KV Store" if count == 1 else f"{count} KV Stores",
            ring,
        )
        all_results.append(result)

    print("\n" + "=" * 60)
    print("PERFORMANCE SUMMARY")
    print("=" * 60)
    print(f"{'Configuration':<20} {'Throughput (ops/s)':<20} {'Latency (ms)':<20} {'Error Rate (%)':<16}")
    print("-" * 60)
    for result in all_results:
        print(
            f"{result['test_name']:<20} {result['throughput']:<20.2f} "
            f"{result['avg_latency']*1000:<20.2f} {result['error_rate']:<16.2f}"
        )

    baseline_throughput = all_results[0]["throughput"]
    baseline_latency = all_results[0]["avg_latency"]

    print("\n" + "-" * 60)
    print("PERFORMANCE DELTA (relative to 1 KV Store)")
    print("-" * 60)
    for i, result in enumerate(all_results):
        if i > 0:
            throughput_delta = ((result["throughput"] - baseline_throughput) / baseline_throughput) * 100
            latency_delta = ((result["avg_latency"] - baseline_latency) / baseline_latency) * 100
            print(
                f"{result['test_name']:<20} Throughput: {throughput_delta:+.2f}% | "
                f"Latency: {latency_delta:+.2f}%"
            )

    with open("benchmark_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print("\n[INFO] Results saved to 'benchmark_results.json'")

    plot_results(all_results)

    print("\n" + "=" * 60)
    print("Benchmark complete!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
