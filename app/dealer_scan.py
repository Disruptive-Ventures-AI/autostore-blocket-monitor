import asyncio
import json
import logging
import re
from urllib.parse import urlparse
import ipaddress

import httpx

from app.config import AD_PAGE_FETCH_DELAY_S, AD_PAGE_FETCH_TIMEOUT_S
from app.models import Car

logger = logging.getLogger(__name__)

DEALER_DOMAINS = [
    "riddermarkbil.se", "riddermark.se", "bilia.se", "bilia.com",
    "hedinbil.se", "hedin.se", "holmgrens.com", "holmgrensbil.se",
    "bavariabil.se", "bavaria.se", "upplands-motor.se", "upplandsmotor.se",
    "bilmetro.se", "kvd.se", "kvd.com", "wayke.se", "kamux.se", "kamux.com",
    "mollerbil.se", "moller.se", "dinbil.se", "bilkompaniet.se",
    "motorcentrum.se", "bildeve.se", "bilvaruhuset.se", "autoexperten.se",
    "smistabil.se", "smistabil.com",
]

_DEALER_PATTERN = re.compile(
    "|".join(re.escape(d) for d in DEALER_DOMAINS), re.IGNORECASE
)

_PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
]


def _is_safe_blocket_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    host = parsed.hostname or ""
    if not host.endswith(".blocket.se") and host != "blocket.se":
        return False

    # Block private IPs
    try:
        ip = ipaddress.ip_address(host)
        for net in _PRIVATE_RANGES:
            if ip in net:
                return False
    except ValueError:
        pass  # hostname, not IP — that's fine

    return True


async def _check_ad_page(client: httpx.AsyncClient, car: Car) -> bool:
    if not _is_safe_blocket_url(car.url):
        return True  # fail-open: can't check, keep the car

    try:
        resp = await client.get(car.url, timeout=AD_PAGE_FETCH_TIMEOUT_S)
        html = resp.text
        if _DEALER_PATTERN.search(html):
            return False  # dealer found
    except Exception:
        pass  # fail-open on errors

    return True  # no dealer URL found, keep the car


async def filter_dealer_urls(cars: list[Car]) -> list[Car]:
    if not cars:
        return []

    result: list[Car] = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for i, car in enumerate(cars):
            keep = await _check_ad_page(client, car)
            if keep:
                result.append(car)
            if i < len(cars) - 1:
                await asyncio.sleep(AD_PAGE_FETCH_DELAY_S)

    filtered = len(cars) - len(result)
    logger.info(json.dumps({
        "event": "dealer_url_scan",
        "input": len(cars),
        "filtered": filtered,
        "remaining": len(result),
    }))
    return result
