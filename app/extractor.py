from app.config import MIL_THRESHOLD
from app.models import Car


def _get(doc: dict, *keys, default=None):
    for key in keys:
        val = doc.get(key)
        if val is not None:
            return val
    return default


def _extract_thumbnail(doc: dict) -> str:
    for field in ("thumbnail", "image"):
        val = doc.get(field)
        if isinstance(val, dict):
            url = val.get("url", "")
            if url:
                return url
        elif isinstance(val, str) and val:
            return val
    images = doc.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            return first.get("url", "")
        if isinstance(first, str):
            return first
    return ""


def _extract_mileage(doc: dict) -> tuple[str | None, int | None]:
    raw = _get(doc, "mileage", "milage")
    if raw is None:
        return None, None
    try:
        val = int(raw)
    except (ValueError, TypeError):
        return str(raw), None
    if val < MIL_THRESHOLD:
        km = val * 10
    else:
        km = val
    return str(raw), km


def _extract_price(doc: dict) -> int | None:
    price = doc.get("price")
    if isinstance(price, dict):
        val = price.get("amount") or price.get("value")
    else:
        val = price
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _extract_location(doc: dict) -> str:
    loc = doc.get("location")
    if isinstance(loc, dict):
        return loc.get("municipality") or loc.get("city") or ""
    if isinstance(loc, str):
        return loc
    return ""


def _extract_year(doc: dict) -> int | None:
    raw = _get(doc, "model_year", "year")
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _extract_make(doc: dict) -> str:
    make = _get(doc, "make", "brand")
    if make:
        return str(make)
    heading = _get(doc, "heading", "subject", "title", "name", default="")
    if heading:
        parts = str(heading).split()
        if parts:
            return parts[0]
    return ""


def extract_car(doc: dict) -> Car:
    ad_id = str(_get(doc, "id", "ad_id", "list_id", default=""))
    mileage_raw, mileage_km = _extract_mileage(doc)
    return Car(
        ad_id=ad_id,
        car_title=str(_get(doc, "heading", "subject", "title", "name", default="")),
        thumbnail=_extract_thumbnail(doc),
        price=_extract_price(doc),
        year=_extract_year(doc),
        mileage_raw=mileage_raw,
        mileage_km=mileage_km,
        make=_extract_make(doc),
        fuel=str(_get(doc, "fuel", "fuel_type", default="")),
        gearbox=str(_get(doc, "gearbox", "transmission", default="")),
        location=_extract_location(doc),
        url=str(_get(doc, "share_url", "url", "canonical_url", default="")),
        dealer_segment=str(_get(doc, "dealer_segment", default="")),
        organisation_name=str(_get(doc, "organisation_name", default="")),
        seller_type=str(_get(doc, "seller_type", "owner_type", default="")),
        org_id=str(_get(doc, "org_id", default="")),
    )


def extract_cars(docs: list[dict]) -> list[Car]:
    cars = []
    for doc in docs:
        car = extract_car(doc)
        if car.ad_id:
            cars.append(car)
    return cars
