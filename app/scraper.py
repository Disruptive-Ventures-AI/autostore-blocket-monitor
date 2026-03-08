import asyncio
import json
import logging

import httpx

from app.config import (
    BLOCKET_API_TIMEOUT_S,
    BLOCKET_API_URL,
    BLOCKET_PAGE_DELAY_S,
    GRACE_GW_API_KEY,
    GRACE_PROXY_URL,
    MAX_PAGES,
    YEAR_FROM,
)

logger = logging.getLogger(__name__)


async def _fetch_page_primary(client: httpx.AsyncClient, page: int) -> list[dict]:
    params = {"page": page, "year_from": YEAR_FROM}
    resp = await client.get(
        BLOCKET_API_URL, params=params, timeout=BLOCKET_API_TIMEOUT_S
    )
    resp.raise_for_status()
    data = resp.json()
    docs = data.get("docs", data.get("response", {}).get("docs", []))
    return docs


async def _fetch_page_grace(client: httpx.AsyncClient, page: int) -> list[dict]:
    url = f"{BLOCKET_API_URL}?page={page}&year_from={YEAR_FROM}"
    resp = await client.post(
        GRACE_PROXY_URL,
        json={"url": url},
        headers={"Content-Type": "application/json", "X-API-Key": GRACE_GW_API_KEY},
        timeout=BLOCKET_API_TIMEOUT_S,
    )
    resp.raise_for_status()
    data = resp.json()
    # Grace may return body as string or already parsed
    body = data.get("body", data)
    if isinstance(body, str):
        body = json.loads(body)
    docs = body.get("docs", body.get("response", {}).get("docs", []))
    return docs


async def fetch_all_pages() -> list[dict]:
    all_docs: list[dict] = []
    async with httpx.AsyncClient() as client:
        for page in range(1, MAX_PAGES + 1):
            try:
                docs = await _fetch_page_primary(client, page)
                if not docs and page == 1:
                    raise ValueError("Empty response from primary API on page 1")
                logger.info(json.dumps({"event": "page_fetched", "source": "primary", "page": page, "count": len(docs)}))
            except Exception:
                logger.warning(json.dumps({"event": "primary_fetch_failed", "page": page}))
                try:
                    docs = await _fetch_page_grace(client, page)
                    logger.info(json.dumps({"event": "page_fetched", "source": "grace", "page": page, "count": len(docs)}))
                except Exception:
                    logger.error(json.dumps({"event": "grace_fetch_failed", "page": page}))
                    docs = []

            all_docs.extend(docs)

            if page < MAX_PAGES:
                await asyncio.sleep(BLOCKET_PAGE_DELAY_S)

    logger.info(json.dumps({"event": "scrape_complete", "total_docs": len(all_docs)}))
    return all_docs
