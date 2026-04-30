import pytest
from unittest.mock import patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../abx-actions/allocate-ip'))
import allocate as handler

class TestAllocateIP:

    def test_handler_returns_ip_on_success(self):
        with patch('allocate.allocate_ip', return_value='10.10.10.55'):
            result = handler.handler(context=None, inputs={'resourceName': 'test-vm-01'})
        assert result['ipAddress'] == '10.10.10.55'
        assert result['allocationStatus'] == 'success'

    def test_handler_raises_on_ipam_failure(self):
        with patch('allocate.allocate_ip', side_effect=ValueError("No free IPs")):
            with pytest.raises(ValueError, match="No free IPs"):
                handler.handler(context=None, inputs={'resourceName': 'test-vm-02'})

    def test_handler_uses_resource_name(self):
        with patch('allocate.allocate_ip', return_value='10.10.10.60') as mock_alloc:
            handler.handler(context=None, inputs={'resourceName': 'my-special-vm'})
            mock_alloc.assert_called_once_with('my-special-vm')

    def test_handler_handles_missing_resource_name(self):
        with patch('allocate.allocate_ip', return_value='10.10.10.61'):
            result = handler.handler(context=None, inputs={})
        assert result['ipAddress'] == '10.10.10.61'