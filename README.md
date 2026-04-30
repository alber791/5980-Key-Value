# 5980 Key-Value Store

## Quick Start

```powershell
docker-compose up --build
python benchmark.py
```

## Architecture

```
Benchmark Client (client-side consistent hashing)
KV Store 1 (8081)
KV Store 2 (8082)
KV Store 3 (8083)
```

## API Endpoints

- `GET /{key}` — Get value
- `PUT /{key}` — Set value
- `POST /{key}` — Set value
- `DELETE /{key}` — Delete key
- `GET /admin/dump` — Dump all keys for diagnostics
- `POST /admin/load` — Bulk load keys
- `POST /admin/reset` — Clear a store for benchmark setup

Example:
```bash
curl -X PUT http://localhost:8081/mykey \
  -H "Content-Type: application/json" \
  -d '{"value": "myvalue"}'
```

## Running with Docker Compose

### Prerequisites
- Docker Desktop or Docker Engine

### Start services

```powershell
docker-compose up --build
```

Services:
- Store 1: `http://localhost:8081`
- Store 2: `http://localhost:8082`
- Store 3: `http://localhost:8083`

### Benchmark-focused defaults

The current configuration is tuned for leaderboard performance:

- Store writes are buffered in memory and flushed periodically instead of on every request.
- Request-by-request logging is disabled by default.
- The benchmark hashes keys directly to the stores instead of adding a router hop.

Useful environment variables:

- `KV_SYNC_WRITES=true` — force immediate durability on every mutation.
- `KV_SAVE_INTERVAL_SECONDS=1.0` — control the periodic flush interval.
- `KV_ENABLE_REQUEST_LOGS=true` — enable per-request logs on the KV stores.

### Run benchmarks

In a seperate terminal, after starting docker, run benchmark.py

```powershell
python benchmark.py
```

Generates:
- `benchmark_results.json` - detailed metrics
- `performance_comparison.png` - throughput/latency/error rate graphs

## Hashing and Benchmarking

Traditional hashing `(key % num_stores)` requires moving all keys when stores change. Consistent hashing uses a virtual ring where:

- Keys hash to positions on a circle
- Each store owns a segment of the ring
- Adding a store only moves ~1/n keys
- Removing a store reassigns that segment's keys

This repo now applies that hashing in the benchmark client, which sends each request directly to the selected store.

The benchmark now measures:

- `set`, `get`, and `delete` operations
- throughput
- average latency
- error rate

## File Overview

- `app.py` - Single KV store service (FastAPI)
- `Dockerfile` - Image for KV store instances
- `docker-compose.yml` - Orchestrates all services
- `benchmark.py` - Performance test
- `requirements.txt` - Dependencies

## Demo Videos

- **With Container**: [ContainerDemo.mp4](ContainerDemo.mp4)