from dataclasses import dataclass
from typing import Optional


@dataclass
class Car:
    ad_id: str
    car_title: str = ""
    thumbnail: str = ""
    price: Optional[int] = None
    year: Optional[int] = None
    mileage_raw: Optional[str] = None
    mileage_km: Optional[int] = None
    make: str = ""
    fuel: str = ""
    gearbox: str = ""
    location: str = ""
    url: str = ""
    dealer_segment: str = ""
    organisation_name: str = ""
    seller_type: str = ""
    org_id: str = ""
    is_priority: bool = False
    ai_vehicle_type: str = ""
