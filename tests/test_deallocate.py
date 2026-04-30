import pytest
from unittest.mock import patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../abx-actions/deallocate-ip'))
import handler

class TestDeallocateIP:

    def test_handler_success(self):
        with patch('handler.delete_ip') as mock_delete:
            result = handler.handler(context=None, inputs={
                'address': '10.10.10.55',
                'resourceName': 'test-vm-01'
            })
        mock_delete.assert_called_once_with('10.10.10.55')
        assert result['deallocationStatus'] == 'success'
        assert result['releasedIp'] == '10.10.10.55'

    def test_handler_skips_when_no_ip(self):
        result = handler.handler(context=None, inputs={'resourceName': 'test-vm-01'})
        assert result['deallocationStatus'] == 'skipped'

    def test_handler_raises_on_delete_failure(self):
        with patch('handler.delete_ip', side_effect=ValueError("Not found")):
            with pytest.raises(ValueError):
                handler.handler(context=None, inputs={
                    'address': '10.10.10.55',
                    'resourceName': 'test-vm-01'
                })