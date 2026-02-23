import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import asyncio
import uvicorn

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI()

# path for data file and log file
DATA_FILE = Path("kv_store.json")
LOG_FILE = "kv_operations.log"

# Logging setup, logs to both console and file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)
logger = logging.getLogger("KVStore")

# Thread-safe (async-safe) storage
store: Dict[str, Any] = {}
store_lock = asyncio.Lock()  # lock for async safety

# functions for loading/saving data to disk
def load_from_disk() -> None:
    global store
    if not DATA_FILE.exists():
        logger.info("No data file found, starting empty")
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        store = data
        logger.info(f"Loaded {len(data)} keys from disk")
    except Exception as e:
        logger.error(f"Failed to load data: {e}")
        store = {}

def save_to_disk() -> None:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(store)} keys to disk")
    except Exception as e:
        logger.error(f"Failed to save data: {e}")

# Load at startup
load_from_disk()

# Models for put request (request bodies need to follow this structure)
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
    duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
    logger.info(
        f"{request.method} {request.url.path} - {response.status_code} - {duration:.2f}ms"
    )
    return response

# ------------ API Endpoints ------------
@app.get("/{key}", response_model=Dict[str, Any])
async def get(key: str):
    #Use lock to ensure thread safety
    async with store_lock:
        if key in store:
            logger.info(f"GET {key} -> OK")
            return {"value": store[key]}
        logger.info(f"GET {key} -> NOT FOUND")
        raise HTTPException(status_code=404, detail="Key not found")

#put or post to create/update key
@app.put("/{key}", status_code=status.HTTP_200_OK)
@app.post("/{key}", status_code=status.HTTP_200_OK)
async def put(key: str, payload: ValuePayload):
    #Use lock to ensure thread safety
    async with store_lock:
        store[key] = payload.value
        logger.info(f"PUT {key} = {payload.value!r}")

    save_to_disk()  # Synchronous save for durability
    return {"status": "ok"}

@app.delete("/{key}", status_code=status.HTTP_200_OK)
async def delete(key: str):
    #Use lock to ensure thread safety
    async with store_lock:
        if key in store:
            del store[key]
            logger.info(f"DEL {key} -> OK")
            save_to_disk()
            return {"status": "deleted"}
        logger.info(f"DEL {key} -> NOT FOUND")
        raise HTTPException(status_code=404, detail="Key not found")


#startup and shutdown events
@app.on_event("startup")
async def startup_event():
    logger.info("KV Store server started")

@app.on_event("shutdown")
async def shutdown_event():
    save_to_disk()  # Final save on shutdown
    logger.info("KV Store server shutting down")

#Run app if executed directly
if __name__ == "__main__":   
    uvicorn.run("app:app", host="127.0.0.1", port=8080, reload=True)