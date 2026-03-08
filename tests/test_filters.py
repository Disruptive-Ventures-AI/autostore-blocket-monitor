import pytest
from app.models import Car
from app.filters import is_dealer_pattern, filter_dealer_patterns, filter_mileage, mark_priority, deduplicate_within_run


def _car(**kwargs) -> Car:
    defaults = {"ad_id": "1"}
    defaults.update(kwargs)
    return Car(**defaults)


class TestDealerPatternCheck1DealerSegment:
    def test_privat_passes(self):
        assert not is_dealer_pattern(_car(dealer_segment="Privat"))

    def test_privat_case_insensitive(self):
        assert not is_dealer_pattern(_car(dealer_segment="privat"))

    def test_foretag_rejected(self):
        assert is_dealer_pattern(_car(dealer_segment="Foretag"))

    def test_empty_segment_passes(self):
        assert not is_dealer_pattern(_car(dealer_segment=""))


class TestDealerPatternCheck2OrgName:
    def test_org_name_present_rejected(self):
        assert is_dealer_pattern(_car(organisation_name="AutoBil AB"))

    def test_org_name_empty_passes(self):
        assert not is_dealer_pattern(_car(organisation_name=""))

    def test_org_name_whitespace_passes(self):
        assert not is_dealer_pattern(_car(organisation_name="   "))


class TestDealerPatternCheck3SellerType:
    def test_professional_rejected(self):
        assert is_dealer_pattern(_car(seller_type="professional"))

    def test_dealer_rejected(self):
        assert is_dealer_pattern(_car(seller_type="dealer"))

    def test_business_rejected(self):
        assert is_dealer_pattern(_car(seller_type="business"))

    def test_private_passes(self):
        assert not is_dealer_pattern(_car(seller_type="private"))


class TestDealerPatternCheck4OrgId:
    def test_org_id_present_rejected(self):
        assert is_dealer_pattern(_car(org_id="12345"))

    def test_org_id_empty_passes(self):
        assert not is_dealer_pattern(_car(org_id=""))


class TestDealerPatternCheck5LeasingPrice:
    def test_price_below_15000_rejected(self):
        assert is_dealer_pattern(_car(price=9999))

    def test_price_at_15000_passes(self):
        assert not is_dealer_pattern(_car(price=15000))

    def test_price_zero_passes(self):
        assert not is_dealer_pattern(_car(price=0))

    def test_price_none_passes(self):
        assert not is_dealer_pattern(_car(price=None))


class TestDealerPatternCheck6LeasingKeywords:
    def test_kr_per_man_rejected(self):
        assert is_dealer_pattern(_car(car_title="BMW 320d 3999 kr/man"))

    def test_kr_per_manad_rejected(self):
        assert is_dealer_pattern(_car(car_title="Volvo V60 kr/manad"))

    def test_privatleasing_rejected(self):
        assert is_dealer_pattern(_car(car_title="Audi A4 privatleasing"))

    def test_ej_leasing_passes(self):
        assert not is_dealer_pattern(_car(car_title="Volvo V60 ej privatleasing"))

    def test_inte_leasing_passes(self):
        assert not is_dealer_pattern(_car(car_title="BMW 320d inte kr/man"))


class TestDealerPatternCheck7BrandNew:
    def test_current_year_low_mileage_rejected(self):
        from datetime import datetime
        current_year = datetime.now().year
        assert is_dealer_pattern(_car(year=current_year, mileage_km=400))

    def test_current_year_normal_mileage_passes(self):
        from datetime import datetime
        current_year = datetime.now().year
        assert not is_dealer_pattern(_car(year=current_year, mileage_km=5000))

    def test_old_year_low_mileage_passes(self):
        assert not is_dealer_pattern(_car(year=2018, mileage_km=100))


class TestDealerPatternCheck8Moms:
    def test_moms_in_title_rejected(self):
        assert is_dealer_pattern(_car(car_title="Volvo XC60 moms"))

    def test_moms_word_boundary(self):
        assert not is_dealer_pattern(_car(car_title="Volvo Momster"))


class TestDealerPatternCheck9Financing:
    def test_ranta_rejected(self):
        assert is_dealer_pattern(_car(car_title="BMW 520d 3% ranta"))

    def test_superdeal_rejected(self):
        assert is_dealer_pattern(_car(car_title="Volvo XC90 Superdeal"))


class TestFilterDealerPatterns:
    def test_filters_dealers(self):
        cars = [
            _car(ad_id="1", dealer_segment="Privat"),
            _car(ad_id="2", dealer_segment="Foretag"),
            _car(ad_id="3", organisation_name="Dealer AB"),
        ]
        result = filter_dealer_patterns(cars)
        assert len(result) == 1
        assert result[0].ad_id == "1"


class TestFilterMileage:
    def test_passenger_under_limit_passes(self):
        cars = [_car(ai_vehicle_type="passenger", mileage_km=150000)]
        result = filter_mileage(cars)
        assert len(result) == 1

    def test_passenger_over_limit_rejected(self):
        cars = [_car(ai_vehicle_type="passenger", mileage_km=250000)]
        result = filter_mileage(cars)
        assert len(result) == 0

    def test_passenger_at_limit_passes(self):
        cars = [_car(ai_vehicle_type="passenger", mileage_km=200000)]
        result = filter_mileage(cars)
        assert len(result) == 1

    def test_commercial_no_limit(self):
        cars = [_car(ai_vehicle_type="commercial", mileage_km=500000)]
        result = filter_mileage(cars)
        assert len(result) == 1

    def test_missing_mileage_included(self):
        cars = [_car(ai_vehicle_type="passenger", mileage_km=None)]
        result = filter_mileage(cars)
        assert len(result) == 1


class TestMarkPriority:
    def test_pickup_is_priority(self):
        cars = [_car(car_title="Ford Ranger Pickup 2020")]
        result = mark_priority(cars)
        assert result[0].is_priority is True

    def test_transporter_is_priority(self):
        cars = [_car(car_title="VW Transporter T6 2019")]
        result = mark_priority(cars)
        assert result[0].is_priority is True

    def test_skapbil_is_priority(self):
        cars = [_car(car_title="Volvo V70 skapbil")]
        result = mark_priority(cars)
        assert result[0].is_priority is True

    def test_regular_car_not_priority(self):
        cars = [_car(car_title="Volvo V60 D4 2021")]
        result = mark_priority(cars)
        assert result[0].is_priority is False


class TestDeduplicateWithinRun:
    def test_removes_duplicates(self):
        cars = [
            _car(ad_id="1", car_title="Car A"),
            _car(ad_id="2", car_title="Car B"),
            _car(ad_id="1", car_title="Car A duplicate"),
        ]
        result = deduplicate_within_run(cars)
        assert len(result) == 2
        assert result[0].ad_id == "1"
        assert result[1].ad_id == "2"
