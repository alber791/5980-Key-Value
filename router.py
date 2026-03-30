import logging
import os
from threading import Lock
from typing import Any, Dict, List
import httpx
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from uhashring import HashRing

# Configuration
DEFAULT_KV_STORES = [
    "http://kv_store_1:8080",
    "http://kv_store_2:8080",
    "http://kv_store_3:8080",
]

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("Router")

app = FastAPI()

def _parse_stores_from_env() -> List[str]:
    env_value = os.getenv("KV_STORES", "").strip()
    if not env_value:
        return DEFAULT_KV_STORES.copy()
    stores = [store.strip() for store in env_value.split(",") if store.strip()]
    return stores or DEFAULT_KV_STORES.copy()


active_stores: List[str] = _parse_stores_from_env()
hash_ring = HashRing(nodes=active_stores)
ring_lock = Lock()

# Request body model
class ValuePayload(BaseModel):
    value: Any


class StoresPayload(BaseModel):
    stores: List[str]
    rebalance: bool = True


@app.on_event("startup")
async def startup_event():
    logger.info(f"Router initialized with {len(active_stores)} KV stores: {active_stores}")


def set_active_stores(stores: List[str]) -> None:
    global active_stores, hash_ring
    unique_stores = list(dict.fromkeys(stores))
    if not unique_stores:
        raise ValueError("At least one backend store is required")
    with ring_lock:
        active_stores = unique_stores
        hash_ring = HashRing(nodes=active_stores)
    logger.info(f"Updated active stores to {len(active_stores)} nodes: {active_stores}")


async def rebalance_keys(previous_stores: List[str]) -> Dict[str, int]:
    moved = 0
    scanned = 0
    errors = 0

    async with httpx.AsyncClient() as client:
        for source_store in previous_stores:
            try:
                dump_response = await client.get(f"{source_store}/admin/dump", timeout=20)
                dump_response.raise_for_status()
                source_data = dump_response.json()
            except Exception as exc:
                logger.error(f"Failed to fetch dump from {source_store}: {exc}")
                errors += 1
                continue

            if not isinstance(source_data, dict):
                logger.error(f"Invalid dump payload from {source_store}")
                errors += 1
                continue

            for key, value in source_data.items():
                scanned += 1
                target_store = get_backend_for_key(key)
                if target_store == source_store:
                    continue

                try:
                    put_response = await client.put(
                        f"{target_store}/{key}",
                        json={"value": value},
                        timeout=20,
                    )
                    put_response.raise_for_status()

                    delete_response = await client.delete(f"{source_store}/{key}", timeout=20)
                    delete_response.raise_for_status()
                    moved += 1
                except Exception as exc:
                    logger.error(
                        f"Failed to move key '{key}' from {source_store} to {target_store}: {exc}"
                    )
                    errors += 1

    logger.info(f"Rebalance complete: scanned={scanned}, moved={moved}, errors={errors}")
    return {"scanned": scanned, "moved": moved, "errors": errors}

#Given a key, determine which backend store to route to based on hashring
def get_backend_for_key(key: str) -> str:
    with ring_lock:
        node = hash_ring.get_node(key)
    if not node:
        raise HTTPException(status_code=503, detail="No backend stores configured")
    return node

#For dev testing, see what is going on in the server
@app.get("/health")
async def health():
    return {"status": "healthy", "stores": active_stores, "store_count": len(active_stores)}

#Change number of active stores for benchmark staging (1, 2, or 3 nodes)
@app.post("/admin/stores", status_code=status.HTTP_200_OK)
async def update_stores(payload: StoresPayload):
    try:
        previous_stores = active_stores.copy()
        set_active_stores(payload.stores)
        rebalance_result = {"scanned": 0, "moved": 0, "errors": 0}

        if payload.rebalance:
            rebalance_result = await rebalance_keys(previous_stores)

        return {
            "status": "ok",
            "stores": active_stores,
            "store_count": len(active_stores),
            "rebalance": rebalance_result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

#Get a key's value from the appropriate KV store
@app.get("/{key}", response_model=Dict[str, Any])
async def get(key: str):
    backend_url = get_backend_for_key(key)
    logger.info(f"GET {key} -> routing to {backend_url}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{backend_url}/{key}", timeout=10)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Key not found")
        logger.error(f"Backend error: {e}")
        raise HTTPException(status_code=500, detail="Backend error")
    except httpx.HTTPError as e:
        logger.error(f"Backend connectivity error: {e}")
        raise HTTPException(status_code=503, detail="Backend unavailable")

#Add or update a key in the appropriate KV store
@app.put("/{key}", status_code=status.HTTP_200_OK)
@app.post("/{key}", status_code=status.HTTP_200_OK)
async def put(key: str, payload: ValuePayload):
    backend_url = get_backend_for_key(key)
    logger.info(f"PUT {key} -> routing to {backend_url}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{backend_url}/{key}",
                json={"value": payload.value},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Backend HTTP error: {e}")
        raise HTTPException(status_code=500, detail="Backend error")
    except httpx.HTTPError as e:
        logger.error(f"Backend error: {e}")
        raise HTTPException(status_code=503, detail="Backend unavailable")

#Delete a key from the appropriate KV store
@app.delete("/{key}", status_code=status.HTTP_200_OK)
async def delete(key: str):
    backend_url = get_backend_for_key(key)
    logger.info(f"DELETE {key} -> routing to {backend_url}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(f"{backend_url}/{key}", timeout=10)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Key not found")
        logger.error(f"Backend error: {e}")
        raise HTTPException(status_code=500, detail="Backend error")
    except httpx.HTTPError as e:
        logger.error(f"Backend connectivity error: {e}")
        raise HTTPException(status_code=503, detail="Backend unavailable")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("router:app", host="0.0.0.0", port=8080, reload=True)
