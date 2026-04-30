# 5980 Key-Value Store

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
- `GET /health` — Health check
- `POST /admin/stores` — Update active backends (optional `rebalance: true`)

Example:
```bash
curl -X PUT http://localhost:8080/mykey \
  -H "Content-Type: application/json" \
  -d '{"value": "myvalue"}'
```

## Running with Docker Compose

### Prerequisites
- Docker Desktop or Docker Engine running
- Python 3.13
- Pipenv

### Start services

```powershell
docker-compose up --build
```

Services:
- Store 1: `http://localhost:8081`
- Store 2: `http://localhost:8082`
- Store 3: `http://localhost:8083`

### Run benchmarks

In a seperate terminal, after starting docker, run benchmark.py

This will run testing on 1, 2, and 3 KV stores and compile and compare the results

```powershell
python benchmark.py
```

Generates:
- `benchmark_results.json` - detailed metrics
- `performance_comparison.png` - throughput/latency graphs

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

## Demo

https://github.com/user-attachments/assets/ee7c3948-dea9-4089-b121-496fbc955571


