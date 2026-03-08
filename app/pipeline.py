import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.classifier import classify_cars
from app.database import get_seen_ad_ids, init_db, write_price_history, write_seen_ads
from app.dealer_scan import filter_dealer_urls
from app.email_service import send_car_emails
from app.extractor import extract_cars
from app.filters import (
    deduplicate_within_run,
    filter_dealer_patterns,
    filter_mileage,
    mark_priority,
)
from app.scraper import fetch_all_pages

logger = logging.getLogger(__name__)

STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")


def _in_operating_hours() -> bool:
    now = datetime.now(STOCKHOLM_TZ)
    # 06:00-00:00 Swedish time: hours 6-23 plus midnight (hour 0)
    return now.hour >= 6 or now.hour == 0


async def run_pipeline() -> dict:
    if not _in_operating_hours():
        logger.info(json.dumps({"event": "outside_operating_hours"}))
        return {"status": "skipped", "reason": "outside operating hours"}

    await init_db()

    # Fetch all pages from Blocket API
    raw_docs = await fetch_all_pages()
    if not raw_docs:
        logger.info(json.dumps({"event": "no_docs_fetched"}))
        await send_car_emails([])
        return {"status": "ok", "new_cars": 0}

    # Extract & normalize
    cars = extract_cars(raw_docs)
    logger.info(json.dumps({"event": "extracted", "count": len(cars)}))

    # Stage 1: Dealer pattern filter
    cars = filter_dealer_patterns(cars)

    # Stage 2: AI classification (fail closed)
    cars = await classify_cars(cars)
    if not cars:
        logger.info(json.dumps({"event": "no_cars_after_classification"}))
        await send_car_emails([])
        return {"status": "ok", "new_cars": 0}

    # Stage 3: Page-level dealer URL scan
    cars = await filter_dealer_urls(cars)

    # Deduplicate within current run
    cars = deduplicate_within_run(cars)

    # Check against seen ads + Stage 4: Mileage filter
    seen_ids = await get_seen_ad_ids()
    new_cars = [c for c in cars if c.ad_id not in seen_ids]
    new_cars = filter_mileage(new_cars)
    logger.info(json.dumps({
        "event": "dedup_complete",
        "before": len(cars),
        "new": len(new_cars),
    }))

    # Mark priority vehicles
    new_cars = mark_priority(new_cars)

    # CRITICAL: Write IDs to seen_ads BEFORE sending email
    await write_seen_ads([c.ad_id for c in new_cars])

    # Write price history (can be parallel with email, but keeping sequential for simplicity)
    await write_price_history(new_cars)

    # Send email
    await send_car_emails(new_cars)

    return {"status": "ok", "new_cars": len(new_cars)}
