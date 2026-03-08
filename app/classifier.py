import json
import logging


import httpx

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_API_URL, ANTHROPIC_MODEL
from app.models import Car

logger = logging.getLogger(__name__)

ACCEPTED_PASSENGER_BRANDS = {"volvo", "audi", "bmw", "volkswagen", "porsche"}

ACCEPTED_COMMERCIAL = {
    "ford": {"ranger", "transit"},
    "nissan": {"navara"},
    "toyota": {"hilux"},
    "volkswagen": {"transporter", "amarok", "caddy", "crafter"},
}

_SYSTEM_PROMPT = """You are a vehicle classifier. Given a car listing, determine:
1. The brand (make) of the vehicle
2. The model of the vehicle
3. Whether it is a "passenger" car or "commercial" vehicle (pickup, van, transport)

Respond ONLY with a JSON object, no markdown:
{"brand": "...", "model": "...", "vehicle_type": "passenger" | "commercial"}"""

_BATCH_SYSTEM_PROMPT = """You are a vehicle classifier. Given car listings, determine for each:
1. The brand (make) of the vehicle
2. The model of the vehicle
3. Whether it is a "passenger" car or "commercial" vehicle (pickup, van, transport)

Respond ONLY with a JSON array containing one object per vehicle in the exact same order. No markdown:
[{"brand": "...", "model": "...", "vehicle_type": "passenger" | "commercial"}, ...]"""

_CLASSIFIER_BATCH_SIZE = 10


def _is_accepted(brand: str, model: str, vtype: str) -> bool:
    if vtype == "commercial":
        if brand in ACCEPTED_COMMERCIAL:
            accepted_models = ACCEPTED_COMMERCIAL[brand]
            if any(m in model for m in accepted_models):
                return True
        if brand in ACCEPTED_PASSENGER_BRANDS:
            return True
    else:
        if brand in ACCEPTED_PASSENGER_BRANDS:
            return True
    return False


async def _classify_batch(cars: list[Car]) -> list[Car] | None:
    batch_text = "\n".join(
        f"{i+1}. {car.car_title} (make field: {car.make}, year: {car.year})"
        for i, car in enumerate(cars)
    )
    prompt = (
        f"Classify each of these {len(cars)} vehicles. "
        f"Return a JSON array with exactly {len(cars)} objects in the same order.\n\n"
        f"{batch_text}"
    )

    try:
        async with httpx.AsyncClient(timeout=60) as http_client:
            resp = await http_client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 1000 + (len(cars) * 100),
                    "system": _BATCH_SYSTEM_PROMPT if len(cars) > 1 else _SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            msg_data = resp.json()
            response_text = msg_data["content"][0]["text"]
        classifications = json.loads(response_text)
        if not isinstance(classifications, list):
            classifications = [classifications]
    except Exception as exc:
        logger.error(json.dumps({"event": "classifier_api_failed", "batch_size": len(cars), "error": str(exc)[:200]}))
        return None  # FAIL CLOSED

    if len(classifications) != len(cars):
        logger.error(json.dumps({
            "event": "classifier_count_mismatch",
            "expected": len(cars),
            "got": len(classifications),
        }))
        return None  # FAIL CLOSED

    accepted: list[Car] = []
    for car, cls in zip(cars, classifications):
        brand = cls.get("brand", "").lower().strip()
        model = cls.get("model", "").lower().strip()
        vtype = cls.get("vehicle_type", "passenger").lower().strip()

        car.ai_vehicle_type = vtype
        car.make = cls.get("brand", car.make)

        if _is_accepted(brand, model, vtype):
            accepted.append(car)

    return accepted


async def classify_cars(cars: list[Car]) -> list[Car]:
    if not cars:
        return []

    if not ANTHROPIC_API_KEY:
        logger.error(json.dumps({"event": "classifier_no_api_key"}))
        return []  # fail closed

    

    all_accepted: list[Car] = []
    for i in range(0, len(cars), _CLASSIFIER_BATCH_SIZE):
        batch = cars[i : i + _CLASSIFIER_BATCH_SIZE]
        result = await _classify_batch(batch)
        if result is None:
            # FAIL CLOSED: any batch failure rejects ALL cars
            logger.error(json.dumps({"event": "classifier_batch_failed_closing"}))
            return []
        all_accepted.extend(result)

    filtered = len(cars) - len(all_accepted)
    logger.info(json.dumps({
        "event": "ai_classification",
        "input": len(cars),
        "accepted": len(all_accepted),
        "filtered": filtered,
    }))
    return all_accepted
