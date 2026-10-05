"""Test DHL Sensors and Calendar Entity."""

import unittest
from unittest.mock import MagicMock

from custom_components.dhl.calendar import DHLTrackingCalendar
from custom_components.dhl.sensor import DHLNextDeliverySensor, DHLParcelSensor

DUMMY_TRACKING_NUMBER = "00340000000000000000"


class TestSensorAndCalendar(unittest.TestCase):
    """Test DHL sensor and calendar entities."""

    def test_next_delivery_sensor(self):
        """Test DHLNextDeliverySensor states and attributes."""
        coordinator = MagicMock()
        coordinator.tracking_numbers = [DUMMY_TRACKING_NUMBER]
        coordinator.data = {
            DUMMY_TRACKING_NUMBER: {
                "id": DUMMY_TRACKING_NUMBER,
                "service": "DHL Paket",
                "status": {
                    "statusCode": "in_transit",
                    "status": "In transit",
                    "description": "Shipment is out for delivery.",
                    "timestamp": "2026-10-05T08:30:00Z",
                    "location": {"address": {"addressLocality": "Bonn"}},
                },
                "estimatedTimeOfDelivery": "2026-10-05T14:00:00Z",
                "details": {
                    "product": {"productName": "DHL Paket"},
                    "weight": {"value": 2.5, "unitText": "kg"},
                },
            }
        }

        entry = MagicMock()
        entry.entry_id = "test_entry"

        sensor = DHLNextDeliverySensor(coordinator, entry)

        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["tracking_number"], DUMMY_TRACKING_NUMBER)
        self.assertEqual(attrs["status_code"], "in_transit")
        self.assertEqual(attrs["service"], "DHL Paket")
        self.assertEqual(attrs["weight"], 2.5)
        self.assertEqual(attrs["weight_unit"], "kg")
        self.assertEqual(attrs["product_name"], "DHL Paket")

    def test_parcel_sensor(self):
        """Test individual DHLParcelSensor entity."""
        coordinator = MagicMock()
        coordinator.tracking_numbers = [DUMMY_TRACKING_NUMBER]
        coordinator.data = {
            DUMMY_TRACKING_NUMBER: {
                "id": DUMMY_TRACKING_NUMBER,
                "status": {
                    "statusCode": "in_transit",
                    "description": "In transit",
                    "timestamp": "2026-10-05T08:30:00Z",
                },
            }
        }
        entry = MagicMock()
        entry.entry_id = "test_entry"

        sensor = DHLParcelSensor(coordinator, entry, DUMMY_TRACKING_NUMBER)
        self.assertEqual(sensor.native_value, "In transit")
        self.assertEqual(
            sensor.extra_state_attributes["tracking_number"], DUMMY_TRACKING_NUMBER
        )

    def test_calendar_entity(self):
        """Test DHLTrackingCalendar compilation of events."""
        coordinator = MagicMock()
        coordinator.tracking_numbers = [DUMMY_TRACKING_NUMBER]
        coordinator.data = {
            DUMMY_TRACKING_NUMBER: {
                "id": DUMMY_TRACKING_NUMBER,
                "status": {
                    "statusCode": "in_transit",
                    "description": "Delivery by 2 PM",
                    "timestamp": "2026-10-05T08:30:00Z",
                },
                "estimatedTimeOfDelivery": "2026-10-05T14:00:00Z",
            }
        }
        entry = MagicMock()
        entry.entry_id = "test_entry"

        calendar = DHLTrackingCalendar(coordinator, entry)
        events = calendar._get_all_events()

        self.assertEqual(len(events), 1)
        self.assertIn(DUMMY_TRACKING_NUMBER, events[0].summary)
        self.assertIn("Delivery by 2 PM", events[0].description)


if __name__ == "__main__":
    unittest.main()
