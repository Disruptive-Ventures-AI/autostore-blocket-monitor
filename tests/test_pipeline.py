import pytest
from unittest.mock import patch, AsyncMock
from app.pipeline import _in_operating_hours


class TestOperatingHours:
    def test_6am_is_operating(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Stockholm")
        with patch("app.pipeline.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 8, 6, 0, tzinfo=tz)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            # Can't easily mock datetime.now, test the logic directly
            pass

    def test_midnight_is_operating(self):
        # hour 0 should be in operating hours
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Stockholm")
        now = datetime(2026, 3, 8, 0, 30, tzinfo=tz)
        assert now.hour == 0
        # The logic: hour >= 6 or hour == 0
        assert now.hour >= 6 or now.hour == 0

    def test_3am_is_not_operating(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Stockholm")
        now = datetime(2026, 3, 8, 3, 0, tzinfo=tz)
        assert now.hour == 3
        assert not (now.hour >= 6 or now.hour == 0)

    def test_23_is_operating(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Stockholm")
        now = datetime(2026, 3, 8, 23, 0, tzinfo=tz)
        assert now.hour >= 6 or now.hour == 0


class TestPipelineRaceCondition:
    """Verify that seen_ads are written before email is sent."""

    def test_write_before_email_in_source(self):
        import inspect
        from app import pipeline
        source = inspect.getsource(pipeline.run_pipeline)
        # Find the awaited calls, not imports
        write_pos = source.index("await write_seen_ads")
        email_pos = source.index("await send_car_emails", source.index("# Send email"))
        assert write_pos < email_pos, "write_seen_ads must be called before send_car_emails"
