import re
import logging
import json
from datetime import datetime

from app.config import PASSENGER_MILEAGE_LIMIT_KM
from app.models import Car

logger = logging.getLogger(__name__)

# Stage 1: Dealer pattern regexes
_LEASING_KW = re.compile(
    r"(kr/m[aå]n|kr/manad|/m[aå]n|privatleasing)",
    re.IGNORECASE,
)
_NEGATION_BEFORE = re.compile(
    r"\b(ej|inte)\s+(kr/m[aå]n|kr/manad|/m[aå]n|privatleasing)",
    re.IGNORECASE,
)
_MOMS_PATTERN = re.compile(r"\bmoms\b", re.IGNORECASE)
_FINANCING_PATTERN = re.compile(r"\d+%\s*r[aä]nta|superdeal", re.IGNORECASE)

# Priority vehicle detection
_PRIORITY_KEYWORDS = [
    "skapbil", "skap", "pickup", "pick-up", "flak", "lastbil", "transport",
    "van", "panel", "cargo", "truck",
    "transporter", "caddy", "crafter", "amarok", "transit", "ranger", "custom",
    "sprinter", "vito", "citan", "ducato", "talento", "fiorino", "doblo",
    "boxer", "partner", "expert", "rifter", "berlingo", "jumper", "jumpy",
    "dispatch", "vivaro", "movano", "combo", "trafic", "master", "kangoo",
    "hiace", "proace", "hilux", "nv200", "nv300", "navara", "primastar",
    "l200", "outlander", "daily", "multivan", "caravelle", "california",
]
_PRIORITY_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _PRIORITY_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def is_dealer_pattern(car: Car) -> bool:
    # Check 1: dealer_segment != "Privat"
    if car.dealer_segment and car.dealer_segment.lower() != "privat":
        return True

    # Check 2: organisation_name present
    if car.organisation_name and car.organisation_name.strip():
        return True

    # Check 3: seller_type is professional/dealer/business
    if car.seller_type and car.seller_type.lower() in ("professional", "dealer", "business"):
        return True

    # Check 4: org_id present
    if car.org_id and car.org_id.strip():
        return True

    # Check 5: price > 0 but < 15,000 SEK (leasing)
    if car.price is not None and 0 < car.price < 15_000:
        return True

    title = car.car_title or ""

    # Check 6: Leasing keywords (with negation exemption)
    if _LEASING_KW.search(title) and not _NEGATION_BEFORE.search(title):
        return True

    # Check 7: Brand new car (model_year >= current year AND mileage < 500)
    current_year = datetime.now().year
    if (
        car.year is not None
        and car.year >= current_year
        and car.mileage_km is not None
        and car.mileage_km < 500
    ):
        return True

    # Check 8: "moms" in title
    if _MOMS_PATTERN.search(title):
        return True

    # Check 9: Financing patterns
    if _FINANCING_PATTERN.search(title):
        return True

    return False


def filter_dealer_patterns(cars: list[Car]) -> list[Car]:
    result = [c for c in cars if not is_dealer_pattern(c)]
    filtered = len(cars) - len(result)
    logger.info(json.dumps({"event": "dealer_filter", "input": len(cars), "filtered": filtered, "remaining": len(result)}))
    return result


def filter_mileage(cars: list[Car]) -> list[Car]:
    result = []
    for car in cars:
        vtype = car.ai_vehicle_type.lower() if car.ai_vehicle_type else ""
        if vtype == "commercial":
            result.append(car)
            continue
        if car.mileage_km is None:
            result.append(car)
            continue
        if car.mileage_km <= PASSENGER_MILEAGE_LIMIT_KM:
            result.append(car)
    filtered = len(cars) - len(result)
    logger.info(json.dumps({"event": "mileage_filter", "input": len(cars), "filtered": filtered, "remaining": len(result)}))
    return result


def mark_priority(cars: list[Car]) -> list[Car]:
    for car in cars:
        if _PRIORITY_PATTERN.search(car.car_title or ""):
            car.is_priority = True
    return cars


def deduplicate_within_run(cars: list[Car]) -> list[Car]:
    seen: set[str] = set()
    result = []
    for car in cars:
        if car.ad_id not in seen:
            seen.add(car.ad_id)
            result.append(car)
    deduped = len(cars) - len(result)
    if deduped:
        logger.info(json.dumps({"event": "intra_run_dedup", "duplicates_removed": deduped}))
    return result
