# 5980 Key-Value Store

## Architecture

```
Client (localhost:8080) 
Router (8080)   
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
- Router: `http://localhost:8080`
- Store 1: `http://localhost:8081`
- Store 2: `http://localhost:8082`
- Store 3: `http://localhost:8083`

### Run benchmarks

In a seperate terminal, after starting docker, run benchmark.py

```powershell
python benchmark.py
```

Generates:
- `benchmark_results.json` - detailed metrics
- `performance_comparison.png` - throughput/latency graphs

## Hashing and Rebalance

Traditional hashing `(key % num_stores)` requires moving all keys when stores change. Consistent hashing uses a virtual ring where:

- Keys hash to positions on a circle
- Each store owns a segment of the ring
- Adding a store only moves ~1/n keys
- Removing a store reassigns that segment's keys

When `/admin/stores` is called, the router can rebalance by:

- Reading each old store's key dump
- Recomputing ownership using the updated ring
- Moving keys to the new owner store

This preserves key reachability across scale up/down events.

## File Overview

- `app.py` - Single KV store service (FastAPI)
- `router.py` - Consistent hashing proxy (routes to backends)
- `Dockerfile` - Image for KV store instances
- `Dockerfile.router` - Image for router service
- `docker-compose.yml` - Orchestrates all services
- `benchmark.py` - Performance test
- `requirements.txt` - Dependencies

## Demo

https://github.com/user-attachments/assets/ee7c3948-dea9-4089-b121-496fbc955571


