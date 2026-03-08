import pytest
from app.models import Car
from app.email_service import _format_mileage, _format_price, _build_html, _build_empty_html, _priority_summary_html


def _car(**kwargs) -> Car:
    defaults = {"ad_id": "1", "car_title": "Test Car"}
    defaults.update(kwargs)
    return Car(**defaults)


class TestFormatMileage:
    def test_mil_format_low_value(self):
        car = _car(mileage_raw="850")
        result = _format_mileage(car)
        assert result == "850 mil (8500 km)"

    def test_km_format_high_value(self):
        car = _car(mileage_raw="120000")
        result = _format_mileage(car)
        assert result == "120000 km"

    def test_missing_mileage(self):
        car = _car(mileage_raw=None)
        result = _format_mileage(car)
        assert result == "Okänd"

    def test_boundary_at_1000(self):
        car = _car(mileage_raw="1000")
        result = _format_mileage(car)
        assert result == "1000 km"

    def test_just_below_1000(self):
        car = _car(mileage_raw="999")
        result = _format_mileage(car)
        assert result == "999 mil (9990 km)"


class TestFormatPrice:
    def test_normal_price(self):
        assert _format_price(250000) == "250 000 kr"

    def test_none_price(self):
        assert _format_price(None) == "Pris saknas"

    def test_small_price(self):
        assert _format_price(15000) == "15 000 kr"


class TestBuildHtml:
    def test_contains_gradient(self):
        cars = [_car(car_title="Volvo V60")]
        html = _build_html(cars)
        assert "#667EEA" in html
        assert "#764BA2" in html

    def test_contains_car_title(self):
        cars = [_car(car_title="BMW 320d 2020")]
        html = _build_html(cars)
        assert "BMW 320d 2020" in html

    def test_priority_badge(self):
        cars = [_car(car_title="Ford Ranger", is_priority=True)]
        html = _build_html(cars)
        assert "#F5A623" in html
        assert "PRIORITET" in html

    def test_priority_cars_sorted_first(self):
        cars = [
            _car(ad_id="1", car_title="Regular Car", is_priority=False),
            _car(ad_id="2", car_title="Priority Van", is_priority=True),
        ]
        html = _build_html(cars)
        priority_pos = html.index("Priority Van")
        regular_pos = html.index("Regular Car")
        assert priority_pos < regular_pos

    def test_batch_info_shown(self):
        cars = [_car()]
        html = _build_html(cars, batch_num=1, total_batches=3)
        assert "(Del 1/3)" in html

    def test_footer_text(self):
        cars = [_car()]
        html = _build_html(cars)
        assert "Autostore Sverige AB" in html

    def test_overview_count(self):
        cars = [_car(ad_id="1"), _car(ad_id="2"), _car(ad_id="3")]
        html = _build_html(cars)
        assert "<strong>3</strong>" in html


class TestPrioritySummary:
    def test_empty_when_no_priority(self):
        assert _priority_summary_html([]) == ""

    def test_contains_table_with_priority_cars(self):
        cars = [
            _car(ad_id="1", car_title="Ford Ranger 2020", is_priority=True, price=350000, year=2020, location="Stockholm"),
            _car(ad_id="2", car_title="VW Transporter", is_priority=True, price=280000, year=2019, location="Göteborg"),
        ]
        html = _priority_summary_html(cars)
        assert "Transport &amp; Pickup" in html
        assert "2 fordon" in html
        assert "Ford Ranger 2020" in html
        assert "VW Transporter" in html
        assert "#F5A623" in html

    def test_summary_appears_in_full_html(self):
        cars = [
            _car(ad_id="1", car_title="Ford Ranger", is_priority=True, price=300000),
            _car(ad_id="2", car_title="Volvo V60", is_priority=False, price=200000),
        ]
        html = _build_html(cars)
        assert "Transport &amp; Pickup" in html
        assert "1 fordon" in html
        assert "transport/pickup" in html
        assert "1 personbilar" in html

    def test_no_summary_section_without_priority(self):
        cars = [_car(ad_id="1", car_title="Volvo V60", is_priority=False)]
        html = _build_html(cars)
        assert "Transport &amp; Pickup" not in html


class TestBuildEmptyHtml:
    def test_contains_no_cars_message(self):
        html = _build_empty_html()
        assert "Inga nya bilar" in html

    def test_contains_gradient(self):
        html = _build_empty_html()
        assert "#667EEA" in html
