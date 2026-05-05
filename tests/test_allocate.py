"""
test_allocate.py
----------------
Unit tests for the Aria Automation ABX Action — phpIPAM IP Allocation.

Tests cover the handler entry point and core allocation logic using
mocked HTTP sessions to avoid live phpIPAM dependency.

Run with:
    pytest tests/test_allocate.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../abx-actions/allocate-ip'))
import allocate


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
    monkeypatch.setenv("SUBNET_ID",   "3")


# ── handler() tests ────────────────────────────────────────────────────────────

class TestAllocateHandler:

    def test_handler_returns_ip_and_status_on_success(self):
        """handler() should return ipAddress, allocationStatus, and subnetId."""
        with patch('allocate._get_session'), \
             patch('allocate.allocate_ip', return_value='10.10.10.55'):
            result = allocate.handler(context=None, inputs={'resourceName': 'test-vm-01'})

        assert result['ipAddress']        == '10.10.10.55'
        assert result['allocationStatus'] == 'success'
        assert 'subnetId' in result

    def test_handler_defaults_resource_name_when_missing(self):
        """handler() should fall back to 'unknown-vm' if resourceName not provided."""
        with patch('allocate._get_session'), \
             patch('allocate.allocate_ip', return_value='10.10.10.61') as mock_alloc:
            allocate.handler(context=None, inputs={})
            _, called_hostname = mock_alloc.call_args[0]
            assert called_hostname == 'unknown-vm'

    def test_handler_passes_resource_name_to_allocate_ip(self):
        """handler() should forward resourceName to allocate_ip as hostname."""
        with patch('allocate._get_session') as mock_get_session, \
             patch('allocate.allocate_ip', return_value='10.10.10.60') as mock_alloc:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            allocate.handler(context=None, inputs={'resourceName': 'my-special-vm'})
            mock_alloc.assert_called_once_with(mock_session, 'my-special-vm')

    def test_handler_raises_on_value_error(self):
        """handler() should propagate ValueError from allocate_ip."""
        with patch('allocate._get_session'), \
             patch('allocate.allocate_ip', side_effect=ValueError("No free IPs")):
            with pytest.raises(ValueError, match="No free IPs"):
                allocate.handler(context=None, inputs={'resourceName': 'test-vm-02'})

    def test_handler_raises_on_environment_error(self):
        """handler() should propagate EnvironmentError from _get_session."""
        with patch('allocate._get_session', side_effect=EnvironmentError("IPAM_TOKEN not set")):
            with pytest.raises(EnvironmentError, match="IPAM_TOKEN not set"):
                allocate.handler(context=None, inputs={'resourceName': 'test-vm-03'})


# ── allocate_ip() tests ────────────────────────────────────────────────────────

class TestAllocateIPFunction:

    def test_allocate_ip_returns_ip_on_success(self, mock_session):
        """allocate_ip() should return the IP string on full success."""
        # Mock GET first_free response
        get_response = MagicMock()
        get_response.json.return_value = {"code": 200, "data": "10.10.10.55"}

        # Mock POST reserve response
        post_response = MagicMock()
        post_response.json.return_value = {"code": 201, "data": {"id": "42"}}

        mock_session.get.return_value  = get_response
        mock_session.post.return_value = post_response

        result = allocate.allocate_ip(mock_session, "test-vm-01")
        assert result == "10.10.10.55"

    def test_allocate_ip_raises_when_no_free_ip(self, mock_session):
        """allocate_ip() should raise ValueError if phpIPAM returns non-200."""
        get_response = MagicMock()
        get_response.json.return_value = {"code": 404, "message": "No free addresses"}
        mock_session.get.return_value = get_response

        with pytest.raises(ValueError, match="phpIPAM returned code 404"):
            allocate.allocate_ip(mock_session, "test-vm-01")

    def test_allocate_ip_raises_when_data_empty(self, mock_session):
        """allocate_ip() should raise ValueError if IP field is missing in response."""
        get_response = MagicMock()
        get_response.json.return_value = {"code": 200, "data": None}
        mock_session.get.return_value = get_response

        with pytest.raises(ValueError, match="no IP address in response"):
            allocate.allocate_ip(mock_session, "test-vm-01")

    def test_allocate_ip_raises_on_failed_reservation(self, mock_session):
        """allocate_ip() should raise ValueError if reservation returns non-201."""
        get_response = MagicMock()
        get_response.json.return_value = {"code": 200, "data": "10.10.10.55"}

        post_response = MagicMock()
        post_response.json.return_value = {"code": 500, "message": "DB error"}

        mock_session.get.return_value  = get_response
        mock_session.post.return_value = post_response

        with pytest.raises(ValueError, match="phpIPAM reservation failed"):
            allocate.allocate_ip(mock_session, "test-vm-01")

    def test_allocate_ip_calls_correct_endpoints(self, mock_session):
        """allocate_ip() should call first_free then addresses endpoints in order."""
        get_response = MagicMock()
        get_response.json.return_value = {"code": 200, "data": "10.10.10.55"}

        post_response = MagicMock()
        post_response.json.return_value = {"code": 201}

        mock_session.get.return_value  = get_response
        mock_session.post.return_value = post_response

        allocate.allocate_ip(mock_session, "test-vm-01")

        get_url = mock_session.get.call_args[0][0]
        post_url = mock_session.post.call_args[0][0]

        assert "first_free" in get_url
        assert "addresses"  in post_url

