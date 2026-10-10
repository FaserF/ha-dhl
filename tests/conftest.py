"""Global fixtures and lightweight Home Assistant test mocks."""

import sys
from unittest.mock import MagicMock

# If homeassistant is not fully installed in the runner environment,
# provide stub modules so lightweight unit tests can run cleanly.
try:
    import homeassistant.helpers.device_registry  # noqa: F401
except ImportError:
    # Build stub module hierarchy
    ha = sys.modules.setdefault("homeassistant", MagicMock())
    ha_comp = sys.modules.setdefault("homeassistant.components", MagicMock())
    ha_sensor = sys.modules.setdefault("homeassistant.components.sensor", MagicMock())
    ha_calendar = sys.modules.setdefault("homeassistant.components.calendar", MagicMock())
    ha_cfg = sys.modules.setdefault("homeassistant.config_entries", MagicMock())
    ha_core = sys.modules.setdefault("homeassistant.core", MagicMock())
    ha_exc = sys.modules.setdefault("homeassistant.exceptions", MagicMock())
    ha_helpers = sys.modules.setdefault("homeassistant.helpers", MagicMock())
    ha_dev_reg = sys.modules.setdefault("homeassistant.helpers.device_registry", MagicMock())
    ha_ep = sys.modules.setdefault("homeassistant.helpers.entity_platform", MagicMock())
    ha_uc = sys.modules.setdefault("homeassistant.helpers.update_coordinator", MagicMock())
    ha_util = sys.modules.setdefault("homeassistant.util", MagicMock())
    ha_dt = sys.modules.setdefault("homeassistant.util.dt", MagicMock())

    class DeviceInfo(dict):
        """Mock DeviceInfo."""
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

    ha_dev_reg.DeviceInfo = DeviceInfo
    ha_helpers.device_registry = ha_dev_reg

    class CoordinatorEntity:
        """Mock CoordinatorEntity."""
        def __init__(self, coordinator, *args, **kwargs):
            self.coordinator = coordinator

    class SensorEntity:
        """Mock SensorEntity."""
        pass

    class CalendarEntity:
        """Mock CalendarEntity."""
        pass

    class CalendarEvent:
        """Mock CalendarEvent."""
        def __init__(self, summary=None, start=None, end=None, description=None, location=None, **kwargs):
            self.summary = summary
            self.start = start
            self.end = end
            self.description = description
            self.location = location

    ha_uc.CoordinatorEntity = CoordinatorEntity
    ha_sensor.SensorEntity = SensorEntity
    ha_calendar.CalendarEntity = CalendarEntity
    ha_calendar.CalendarEvent = CalendarEvent
