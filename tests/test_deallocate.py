"""
test_deallocate.py
------------------
Unit tests for the Aria Automation ABX Action — phpIPAM IP Deallocation.

Tests cover the handler entry point and core deallocation logic using
mocked HTTP sessions to avoid live phpIPAM dependency.

Run with:
    pytest tests/test_deallocate.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../abx-actions/deallocate-ip'))
import deallocate


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_session():
    """Return a MagicMock that mimics a requests.Session."""
    return MagicMock()


@pytest.fixture(autouse=True)
def set_env_vars(monkeypatch):
    """Ensure required environment variables are set for every test."""
    monkeypatch.setenv("IPAM_URL",    "https://ipam.test/api")
    monkeypatch.setenv("IPAM_APP_ID", "aria")
    monkeypatch.setenv("IPAM_TOKEN",  "test-token-abc")


# ── handler() tests ────────────────────────────────────────────────────────────

class TestDeallocateHandler:

    def test_handler_returns_success_on_valid_ip(self):
        """handler() should return ipAddress and deallocationStatus on success."""
        with patch('deallocate._get_session'), \
             patch('deallocate.deallocate_ip') as mock_dealloc:
            result = deallocate.handler(
                context=None,
                inputs={'ipAddress': '10.10.10.55', 'resourceName': 'test-vm-01'}
            )

        mock_dealloc.assert_called_once()
        assert result['ipAddress']          == '10.10.10.55'
        assert result['deallocationStatus'] == 'success'

    def test_handler_raises_when_ip_address_missing(self):
        """handler() should raise ValueError if ipAddress is not in inputs."""
        with pytest.raises(ValueError, match="ipAddress.*required"):
            deallocate.handler(
                context=None,
                inputs={'resourceName': 'test-vm-01'}
            )

    def test_handler_raises_on_value_error_from_deallocate_ip(self):
        """handler() should propagate ValueError from deallocate_ip."""
        with patch('deallocate._get_session'), \
             patch('deallocate.deallocate_ip', side_effect=ValueError("Not found")):
            with pytest.raises(ValueError, match="Not found"):
                deallocate.handler(
                    context=None,
                    inputs={'ipAddress': '10.10.10.55', 'resourceName': 'test-vm-01'}
                )

    def test_handler_raises_on_environment_error(self):
        """handler() should propagate EnvironmentError from _get_session."""
        with patch('deallocate._get_session', side_effect=EnvironmentError("IPAM_TOKEN not set")):
            with pytest.raises(EnvironmentError, match="IPAM_TOKEN not set"):
                deallocate.handler(
                    context=None,
                    inputs={'ipAddress': '10.10.10.55', 'resourceName': 'test-vm-01'}
                )

    def test_handler_defaults_resource_name_when_missing(self):
        """handler() should fall back to 'unknown-vm' if resourceName not provided."""
        with patch('deallocate._get_session'), \
             patch('deallocate.deallocate_ip') as mock_dealloc:
            deallocate.handler(
                context=None,
                inputs={'ipAddress': '10.10.10.55'}
            )
        _, _, called_resource = mock_dealloc.call_args[0]
        assert called_resource == 'unknown-vm'


# ── deallocate_ip() tests ──────────────────────────────────────────────────────

class TestDeallocateIPFunction:

    def test_deallocate_ip_success(self, mock_session):
        """deallocate_ip() should search, find, and delete the IP record."""
        search_response = MagicMock()
        search_response.json.return_value = {
            "code": 200,
            "data": [{"id": "42", "ip": "10.10.10.55", "hostname": "test-vm-01"}]
        }

        delete_response = MagicMock()
        delete_response.json.return_value = {"code": 200, "message": "Deleted"}

        mock_session.get.return_value    = search_response
        mock_session.delete.return_value = delete_response

        # Should not raise
        deallocate.deallocate_ip(mock_session, "10.10.10.55", "test-vm-01")

        mock_session.get.assert_called_once()
        mock_session.delete.assert_called_once()

    def test_deallocate_ip_raises_when_ip_not_found(self, mock_session):
        """deallocate_ip() should raise ValueError if search returns no records."""
        search_response = MagicMock()
        search_response.json.return_value = {"code": 200, "data": []}
        mock_session.get.return_value = search_response

        with pytest.raises(ValueError, match="No phpIPAM record found"):
            deallocate.deallocate_ip(mock_session, "10.10.10.99", "test-vm-01")

    def test_deallocate_ip_raises_on_search_error(self, mock_session):
        """deallocate_ip() should raise ValueError if phpIPAM search returns non-200."""
        search_response = MagicMock()
        search_response.json.return_value = {"code": 404, "message": "Not found"}
        mock_session.get.return_value = search_response

        with pytest.raises(ValueError, match="phpIPAM search returned code 404"):
            deallocate.deallocate_ip(mock_session, "10.10.10.55", "test-vm-01")

    def test_deallocate_ip_raises_on_delete_failure(self, mock_session):
        """deallocate_ip() should raise ValueError if DELETE returns non-200."""
        search_response = MagicMock()
        search_response.json.return_value = {
            "code": 200,
            "data": [{"id": "42", "ip": "10.10.10.55"}]
        }

        delete_response = MagicMock()
        delete_response.json.return_value = {"code": 500, "message": "DB error"}

        mock_session.get.return_value    = search_response
        mock_session.delete.return_value = delete_response

        with pytest.raises(ValueError, match="phpIPAM deletion failed"):
            deallocate.deallocate_ip(mock_session, "10.10.10.55", "test-vm-01")

    def test_deallocate_ip_calls_correct_endpoints(self, mock_session):
        """deallocate_ip() should call search then delete endpoints in order."""
        search_response = MagicMock()
        search_response.json.return_value = {
            "code": 200,
            "data": [{"id": "42", "ip": "10.10.10.55"}]
        }

        delete_response = MagicMock()
        delete_response.json.return_value = {"code": 200}

        mock_session.get.return_value    = search_response
        mock_session.delete.return_value = delete_response

        deallocate.deallocate_ip(mock_session, "10.10.10.55", "test-vm-01")

        get_url    = mock_session.get.call_args[0][0]
        delete_url = mock_session.delete.call_args[0][0]

        assert "search/10.10.10.55" in get_url
        assert "addresses/42"       in delete_url
