import pytest
from app.dealer_scan import _is_safe_blocket_url


class TestSsrfProtection:
    def test_valid_blocket_url(self):
        assert _is_safe_blocket_url("https://www.blocket.se/annons/12345") is True

    def test_subdomain_blocket(self):
        assert _is_safe_blocket_url("https://bil.blocket.se/annons/12345") is True

    def test_blocket_root(self):
        assert _is_safe_blocket_url("https://blocket.se/annons/12345") is True

    def test_non_blocket_domain_rejected(self):
        assert _is_safe_blocket_url("https://evil.com/blocket.se") is False

    def test_private_ip_rejected(self):
        assert _is_safe_blocket_url("http://192.168.1.1/page") is False

    def test_localhost_rejected(self):
        assert _is_safe_blocket_url("http://127.0.0.1/page") is False

    def test_metadata_endpoint_rejected(self):
        assert _is_safe_blocket_url("http://169.254.169.254/latest/meta-data") is False

    def test_empty_url_rejected(self):
        assert _is_safe_blocket_url("") is False

    def test_fake_blocket_suffix_rejected(self):
        assert _is_safe_blocket_url("https://notblocket.se/annons/12345") is False

    def test_10_range_rejected(self):
        assert _is_safe_blocket_url("http://10.0.0.1/page") is False

    def test_172_range_rejected(self):
        assert _is_safe_blocket_url("http://172.16.0.1/page") is False
