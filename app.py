import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from contextlib import suppress
from typing import Any, Dict, Optional
import asyncio
import uvicorn

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI()

# path for data file and log file
DATA_FILE = Path(os.getenv("KV_DATA_FILE", "/app/data/kv_store.json"))
LOG_FILE = os.getenv("KV_LOG_FILE", "/app/data/kv_operations.log")
LOG_LEVEL = os.getenv("KV_LOG_LEVEL", "WARNING").upper()
ENABLE_REQUEST_LOGS = os.getenv("KV_ENABLE_REQUEST_LOGS", "false").lower() == "true"
SYNC_WRITES = os.getenv("KV_SYNC_WRITES", "false").lower() == "true"
SAVE_INTERVAL_SECONDS = float(os.getenv("KV_SAVE_INTERVAL_SECONDS", "1.0"))

DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

# Logging setup, logs to both console and file
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.WARNING),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)
logger = logging.getLogger("KVStore")

# Thread-safe storage
store: Dict[str, Any] = {}
store_lock = asyncio.Lock()  # lock for async safety
store_version = 0
last_persisted_version = 0
save_task: Optional[asyncio.Task] = None


def log_request(message: str) -> None:
    if ENABLE_REQUEST_LOGS:
        logger.info(message)

# functions for loading/saving data to disk
def load_from_disk() -> None:
    global store, store_version, last_persisted_version
    if not DATA_FILE.exists():
        logger.info("No data file found, starting empty")
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        store = data
        store_version = len(store)
        last_persisted_version = store_version
        logger.info(f"Loaded {len(data)} keys from disk")
    except Exception as e:
        logger.error(f"Failed to load data: {e}")
        store = {}


def save_to_disk(snapshot: Dict[str, Any]) -> None:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, separators=(",", ":"))
        logger.info(f"Saved {len(snapshot)} keys to disk")
    except Exception as e:
        logger.error(f"Failed to save data: {e}")


async def persist_store(force: bool = False) -> bool:
    global last_persisted_version

    async with store_lock:
        target_version = store_version
        if not force and target_version == last_persisted_version:
            return False
        snapshot = dict(store)

    save_to_disk(snapshot)
    last_persisted_version = max(last_persisted_version, target_version)
    return True


async def periodic_persist() -> None:
    while True:
        await asyncio.sleep(SAVE_INTERVAL_SECONDS)
        await persist_store()

# Load at startup
load_from_disk()

# Models for put request
"""
{
		"value": "some_value"
}
"""
class ValuePayload(BaseModel):
    value: Any

#Middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now(timezone.utc)
    response = await call_next(request)
    if ENABLE_REQUEST_LOGS:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} - {duration:.2f}ms"
        )
    return response

# ------------ API Endpoints ------------
@app.get("/{key}", response_model=Dict[str, Any])
async def get(key: str):
    if key in store:
        log_request(f"GET {key} -> OK")
        return {"value": store[key]}
    log_request(f"GET {key} -> NOT FOUND")
    raise HTTPException(status_code=404, detail="Key not found")

#put or post to create/update key
@app.put("/{key}", status_code=status.HTTP_200_OK)
@app.post("/{key}", status_code=status.HTTP_200_OK)
async def put(key: str, payload: ValuePayload):
    global store_version
    #Use lock to ensure thread safety
    async with store_lock:
        store[key] = payload.value
        store_version += 1
        log_request(f"PUT {key} = {payload.value!r}")

    if SYNC_WRITES:
        await persist_store(force=True)
    return {"status": "ok"}

@app.delete("/{key}", status_code=status.HTTP_200_OK)
async def delete(key: str):
    global store_version
    #Use lock to ensure thread safety
    async with store_lock:
        if key in store:
            del store[key]
            store_version += 1
            log_request(f"DEL {key} -> OK")
        else:
            log_request(f"DEL {key} -> NOT FOUND")
            raise HTTPException(status_code=404, detail="Key not found")

    if SYNC_WRITES:
        await persist_store(force=True)
    return {"status": "deleted"}


@app.get("/admin/dump", response_model=Dict[str, Any])
async def admin_dump():
    async with store_lock:
        return dict(store)


@app.post("/admin/reset", status_code=status.HTTP_200_OK)
async def admin_reset():
    global store_version
    async with store_lock:
        cleared = len(store)
        store.clear()
        store_version += max(cleared, 1)

    if SYNC_WRITES:
        await persist_store(force=True)
    return {"status": "ok", "cleared": cleared}


@app.post("/admin/load", status_code=status.HTTP_200_OK)
async def admin_load(payload: Dict[str, Any]):
    global store_version
    async with store_lock:
        store.update(payload)
        store_version += len(payload) or 1
        logger.info(f"ADMIN LOAD -> merged {len(payload)} keys")

    if SYNC_WRITES:
        await persist_store(force=True)
    return {"status": "ok", "loaded": len(payload)}


#startup and shutdown events
@app.on_event("startup")
async def startup_event():
    global save_task
    if not SYNC_WRITES:
        save_task = asyncio.create_task(periodic_persist())
    logger.info("KV Store server started")

@app.on_event("shutdown")
async def shutdown_event():
    global save_task
    if save_task is not None:
        save_task.cancel()
        with suppress(asyncio.CancelledError):
            await save_task
    await persist_store(force=True)
    logger.info("KV Store server shutting down")

#Run app if executed directly
if __name__ == "__main__":   
    uvicorn.run("app:app", host="127.0.0.1", port=8080, reload=True)