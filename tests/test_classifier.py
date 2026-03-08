import pytest
from app.classifier import _is_accepted


class TestIsAccepted:
    def test_passenger_volvo_accepted(self):
        assert _is_accepted("volvo", "xc60", "passenger") is True

    def test_passenger_audi_accepted(self):
        assert _is_accepted("audi", "a4", "passenger") is True

    def test_passenger_bmw_accepted(self):
        assert _is_accepted("bmw", "320d", "passenger") is True

    def test_passenger_volkswagen_accepted(self):
        assert _is_accepted("volkswagen", "golf", "passenger") is True

    def test_passenger_porsche_accepted(self):
        assert _is_accepted("porsche", "cayenne", "passenger") is True

    def test_passenger_ford_rejected(self):
        assert _is_accepted("ford", "focus", "passenger") is False

    def test_passenger_toyota_rejected(self):
        assert _is_accepted("toyota", "corolla", "passenger") is False

    def test_commercial_ford_ranger_accepted(self):
        assert _is_accepted("ford", "ranger", "commercial") is True

    def test_commercial_ford_transit_accepted(self):
        assert _is_accepted("ford", "transit", "commercial") is True

    def test_commercial_ford_focus_rejected(self):
        assert _is_accepted("ford", "focus", "commercial") is False

    def test_commercial_nissan_navara_accepted(self):
        assert _is_accepted("nissan", "navara", "commercial") is True

    def test_commercial_nissan_qashqai_rejected(self):
        assert _is_accepted("nissan", "qashqai", "commercial") is False

    def test_commercial_toyota_hilux_accepted(self):
        assert _is_accepted("toyota", "hilux", "commercial") is True

    def test_commercial_toyota_corolla_rejected(self):
        assert _is_accepted("toyota", "corolla", "commercial") is False

    def test_commercial_vw_transporter_accepted(self):
        assert _is_accepted("volkswagen", "transporter", "commercial") is True

    def test_commercial_vw_amarok_accepted(self):
        assert _is_accepted("volkswagen", "amarok", "commercial") is True

    def test_commercial_vw_caddy_accepted(self):
        assert _is_accepted("volkswagen", "caddy", "commercial") is True

    def test_commercial_vw_crafter_accepted(self):
        assert _is_accepted("volkswagen", "crafter", "commercial") is True

    def test_commercial_volvo_any_accepted(self):
        # Volvo is an accepted passenger brand so all models pass
        assert _is_accepted("volvo", "fh16", "commercial") is True

    def test_unknown_brand_rejected(self):
        assert _is_accepted("renault", "clio", "passenger") is False
