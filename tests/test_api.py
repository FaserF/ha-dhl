"""Test DHL API Client and Coordinator logic."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from custom_components.dhl.api import (
    DHLAPIClient,
    DHLAuthError,
    DHLRateLimitError,
)

DUMMY_TRACKING_NUMBER = "00340000000000000000"


class TestDHLAPIClient(unittest.IsolatedAsyncioTestCase):
    """Test DHL API Client."""

    async def test_api_client_success(self):
        """Test successful shipment lookup."""
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={
                "shipments": [
                    {
                        "id": DUMMY_TRACKING_NUMBER,
                        "service": "DHL Paket",
                        "status": {
                            "statusCode": "in_transit",
                            "status": "In Zustellung",
                            "description": "Die Sendung befindet sich in der Zustellung.",
                            "timestamp": "2026-10-05T08:30:00Z",
                        },
                        "estimatedTimeOfDelivery": "2026-10-05T14:00:00Z",
                    }
                ]
            }
        )

        session.get.return_value.__aenter__.return_value = mock_resp

        client = DHLAPIClient(session=session, api_key="dummy_key")
        shipment = await client.get_shipment(DUMMY_TRACKING_NUMBER)

        self.assertIsNotNone(shipment)
        self.assertEqual(shipment["id"], DUMMY_TRACKING_NUMBER)
        self.assertEqual(shipment["status"]["statusCode"], "in_transit")
        self.assertEqual(shipment["estimatedTimeOfDelivery"], "2026-10-05T14:00:00Z")

    async def test_api_client_auth_error(self):
        """Test 401/403 authentication error handling."""
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 401
        mock_resp.text = AsyncMock(return_value="Unauthorized")
        session.get.return_value.__aenter__.return_value = mock_resp

        client = DHLAPIClient(session=session, api_key="invalid_key")
        with self.assertRaises(DHLAuthError):
            await client.get_shipment(DUMMY_TRACKING_NUMBER)

    async def test_api_client_rate_limit(self):
        """Test 429 rate limit exception."""
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 429
        mock_resp.text = AsyncMock(return_value="Too Many Requests")
        session.get.return_value.__aenter__.return_value = mock_resp

        client = DHLAPIClient(session=session, api_key="dummy_key")
        with self.assertRaises(DHLRateLimitError):
            await client.get_shipment(DUMMY_TRACKING_NUMBER)

    async def test_api_client_not_found(self):
        """Test 404 returns None."""
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 404
        session.get.return_value.__aenter__.return_value = mock_resp

        client = DHLAPIClient(session=session, api_key="dummy_key")
        result = await client.get_shipment("nonexistent_number")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
