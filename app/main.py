import hmac
import json
import logging
import sys

from fastapi import FastAPI, Header, HTTPException

from app.config import TRIGGER_API_KEY
from app.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Blocket Bilbevakning", version="1.0.0")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/trigger")
async def trigger(x_api_key: str = Header(alias="X-API-Key")):
    if not TRIGGER_API_KEY:
        raise HTTPException(status_code=500, detail="TRIGGER_API_KEY not configured")

    if not x_api_key or not hmac.compare_digest(x_api_key, TRIGGER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")

    logger.info(json.dumps({"event": "trigger_received"}))
    result = await run_pipeline()
    logger.info(json.dumps({"event": "pipeline_complete", "result": result}))
    return result
