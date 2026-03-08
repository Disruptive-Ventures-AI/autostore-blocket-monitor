import pytest
from app.extractor import extract_car, extract_cars


class TestExtractCar:
    def test_basic_extraction(self):
        doc = {
            "id": "12345",
            "heading": "Volvo V60 2021",
            "price": {"amount": 250000},
            "model_year": 2021,
            "mileage": 8500,
            "make": "Volvo",
            "fuel": "Diesel",
            "gearbox": "Automat",
            "location": {"municipality": "Stockholm"},
            "share_url": "https://www.blocket.se/annons/12345",
            "dealer_segment": "Privat",
        }
        car = extract_car(doc)
        assert car.ad_id == "12345"
        assert car.car_title == "Volvo V60 2021"
        assert car.price == 250000
        assert car.year == 2021
        assert car.mileage_km == 85000  # 8500 < 50000, treated as mil * 10
        assert car.make == "Volvo"
        assert car.fuel == "Diesel"
        assert car.gearbox == "Automat"
        assert car.location == "Stockholm"
        assert car.url == "https://www.blocket.se/annons/12345"
        assert car.dealer_segment == "Privat"

    def test_id_fallback_ad_id(self):
        doc = {"ad_id": "99"}
        car = extract_car(doc)
        assert car.ad_id == "99"

    def test_id_fallback_list_id(self):
        doc = {"list_id": "77"}
        car = extract_car(doc)
        assert car.ad_id == "77"

    def test_make_fallback_to_brand(self):
        doc = {"id": "1", "brand": "BMW"}
        car = extract_car(doc)
        assert car.make == "BMW"

    def test_make_fallback_to_heading(self):
        doc = {"id": "1", "heading": "Audi A4 2019"}
        car = extract_car(doc)
        assert car.make == "Audi"

    def test_make_no_fallback(self):
        doc = {"id": "1"}
        car = extract_car(doc)
        assert car.make == ""

    def test_price_as_dict_value(self):
        doc = {"id": "1", "price": {"value": 199000}}
        car = extract_car(doc)
        assert car.price == 199000

    def test_price_as_int(self):
        doc = {"id": "1", "price": 150000}
        car = extract_car(doc)
        assert car.price == 150000

    def test_price_missing(self):
        doc = {"id": "1"}
        car = extract_car(doc)
        assert car.price is None

    def test_mileage_high_value_is_km(self):
        doc = {"id": "1", "mileage": 120000}
        car = extract_car(doc)
        assert car.mileage_km == 120000  # >= 50000, treated as km

    def test_mileage_low_value_is_mil(self):
        doc = {"id": "1", "mileage": 4500}
        car = extract_car(doc)
        assert car.mileage_km == 45000  # < 50000, treated as mil * 10

    def test_mileage_missing(self):
        doc = {"id": "1"}
        car = extract_car(doc)
        assert car.mileage_raw is None
        assert car.mileage_km is None

    def test_mileage_milage_typo_field(self):
        doc = {"id": "1", "milage": 7000}
        car = extract_car(doc)
        assert car.mileage_km == 70000

    def test_thumbnail_as_string(self):
        doc = {"id": "1", "thumbnail": "https://img.example.com/1.jpg"}
        car = extract_car(doc)
        assert car.thumbnail == "https://img.example.com/1.jpg"

    def test_thumbnail_as_dict(self):
        doc = {"id": "1", "thumbnail": {"url": "https://img.example.com/2.jpg"}}
        car = extract_car(doc)
        assert car.thumbnail == "https://img.example.com/2.jpg"

    def test_thumbnail_from_images_list(self):
        doc = {"id": "1", "images": [{"url": "https://img.example.com/3.jpg"}]}
        car = extract_car(doc)
        assert car.thumbnail == "https://img.example.com/3.jpg"

    def test_thumbnail_from_images_string_list(self):
        doc = {"id": "1", "images": ["https://img.example.com/4.jpg"]}
        car = extract_car(doc)
        assert car.thumbnail == "https://img.example.com/4.jpg"

    def test_location_as_dict_municipality(self):
        doc = {"id": "1", "location": {"municipality": "Goteborg"}}
        car = extract_car(doc)
        assert car.location == "Goteborg"

    def test_location_as_dict_city(self):
        doc = {"id": "1", "location": {"city": "Malmo"}}
        car = extract_car(doc)
        assert car.location == "Malmo"

    def test_location_as_string(self):
        doc = {"id": "1", "location": "Uppsala"}
        car = extract_car(doc)
        assert car.location == "Uppsala"

    def test_url_fallback_order(self):
        doc = {"id": "1", "url": "https://blocket.se/1", "canonical_url": "https://blocket.se/2"}
        car = extract_car(doc)
        # share_url takes priority but is absent, so url is used
        assert car.url == "https://blocket.se/1"

    def test_seller_type_fallback(self):
        doc = {"id": "1", "owner_type": "private"}
        car = extract_car(doc)
        assert car.seller_type == "private"


class TestExtractCars:
    def test_filters_empty_ad_id(self):
        docs = [{"id": "1"}, {"heading": "No ID car"}, {"id": "3"}]
        cars = extract_cars(docs)
        assert len(cars) == 2
        assert cars[0].ad_id == "1"
        assert cars[1].ad_id == "3"

    def test_empty_input(self):
        assert extract_cars([]) == []
