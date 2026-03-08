import asyncio
import os
import tempfile
import pytest
from unittest.mock import patch

from app.database import init_db, get_seen_ad_ids, write_seen_ads, write_price_history, get_run_state, set_run_state
from app.models import Car


@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    with patch("app.database.DATABASE_PATH", db_path):
        yield db_path
    os.unlink(db_path)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestDatabase:
    def test_init_db(self, tmp_db):
        _run(init_db())
        # Should not raise

    def test_write_and_read_seen_ads(self, tmp_db):
        _run(init_db())
        _run(write_seen_ads(["ad1", "ad2", "ad3"]))
        seen = _run(get_seen_ad_ids())
        assert seen == {"ad1", "ad2", "ad3"}

    def test_duplicate_seen_ads_ignored(self, tmp_db):
        _run(init_db())
        _run(write_seen_ads(["ad1"]))
        _run(write_seen_ads(["ad1"]))  # Should not raise
        seen = _run(get_seen_ad_ids())
        assert seen == {"ad1"}

    def test_empty_write(self, tmp_db):
        _run(init_db())
        _run(write_seen_ads([]))
        seen = _run(get_seen_ad_ids())
        assert seen == set()

    def test_price_history(self, tmp_db):
        _run(init_db())
        cars = [
            Car(ad_id="1", car_title="Volvo V60", make="Volvo", year=2021,
                mileage_raw="8500", mileage_km=85000, price=250000,
                fuel="Diesel", gearbox="Automat", location="Stockholm",
                url="https://blocket.se/1"),
        ]
        _run(write_price_history(cars))
        # Should not raise

    def test_run_state(self, tmp_db):
        _run(init_db())
        result = _run(get_run_state("test_key"))
        assert result is None

        _run(set_run_state("test_key", "test_value"))
        result = _run(get_run_state("test_key"))
        assert result == "test_value"

        _run(set_run_state("test_key", "new_value"))
        result = _run(get_run_state("test_key"))
        assert result == "new_value"
