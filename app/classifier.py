import json
import logging

import anthropic

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
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


async def classify_cars(cars: list[Car]) -> list[Car]:
    if not cars:
        return []

    if not ANTHROPIC_API_KEY:
        logger.error(json.dumps({"event": "classifier_no_api_key"}))
        return []  # fail closed

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    batch_text = "\n".join(
        f"- {car.car_title} (make field: {car.make}, year: {car.year})"
        for car in cars
    )
    prompt = (
        f"Classify each of these {len(cars)} vehicles. "
        f"Return a JSON array with one object per vehicle in the same order.\n\n"
        f"{batch_text}"
    )

    try:
        message = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text
        classifications = json.loads(response_text)
        if not isinstance(classifications, list):
            classifications = [classifications]
    except Exception:
        logger.error(json.dumps({"event": "classifier_api_failed"}))
        return []  # FAIL CLOSED

    if len(classifications) != len(cars):
        logger.error(json.dumps({
            "event": "classifier_count_mismatch",
            "expected": len(cars),
            "got": len(classifications),
        }))
        return []  # fail closed

    accepted: list[Car] = []
    for car, cls in zip(cars, classifications):
        brand = cls.get("brand", "").lower().strip()
        model = cls.get("model", "").lower().strip()
        vtype = cls.get("vehicle_type", "passenger").lower().strip()

        car.ai_vehicle_type = vtype
        car.make = cls.get("brand", car.make)

        if vtype == "commercial":
            # Check if brand+model combo is accepted
            if brand in ACCEPTED_COMMERCIAL:
                accepted_models = ACCEPTED_COMMERCIAL[brand]
                if any(m in model for m in accepted_models):
                    accepted.append(car)
                    continue
            # Also accept if brand is in passenger brands (e.g. VW Transporter)
            if brand in ACCEPTED_PASSENGER_BRANDS:
                accepted.append(car)
                continue
        else:
            if brand in ACCEPTED_PASSENGER_BRANDS:
                accepted.append(car)
                continue

    filtered = len(cars) - len(accepted)
    logger.info(json.dumps({
        "event": "ai_classification",
        "input": len(cars),
        "accepted": len(accepted),
        "filtered": filtered,
    }))
    return accepted
