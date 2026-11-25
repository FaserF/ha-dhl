"""Tests for the DHL integration."""

import sys
from datetime import UTC, date, datetime
from unittest.mock import MagicMock


class HAMock(MagicMock):
    @classmethod
    def __getattr__(cls, name: str) -> MagicMock:
        return MagicMock()


# Base class for entities to avoid metaclass conflict with MagicMock
class BaseEntity:
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, *args, **kwargs):
        pass


class CoordinatorEntity(BaseEntity):
    def __init__(self, coordinator=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.coordinator = coordinator


class CalendarEntity(BaseEntity):
    pass


class SensorEntity(BaseEntity):
    pass


class CalendarEvent:
    def __init__(self, summary, start, end, description=None, location=None):
        self.summary = summary
        self.start = start
        self.end = end
        self.description = description
        self.location = location


# Universal mock for homeassistant
sys.modules["homeassistant"] = HAMock()
sys.modules["homeassistant.core"] = HAMock()
sys.modules["homeassistant.config_entries"] = HAMock()
sys.modules["homeassistant.exceptions"] = HAMock()
sys.modules["homeassistant.helpers"] = HAMock()
sys.modules["homeassistant.helpers.issue_registry"] = HAMock()
sys.modules["homeassistant.helpers.storage"] = HAMock()
sys.modules["homeassistant.helpers.aiohttp_client"] = HAMock()
sys.modules["homeassistant.helpers.update_coordinator"] = HAMock()
sys.modules["homeassistant.helpers.entity"] = HAMock()
sys.modules["homeassistant.helpers.entity_platform"] = HAMock()
sys.modules["homeassistant.components.sensor"] = HAMock()
sys.modules["homeassistant.components.calendar"] = HAMock()
sys.modules["homeassistant.const"] = HAMock()
sys.modules["homeassistant.util"] = HAMock()
dt_mock = HAMock()
dt_mock.now = lambda: datetime.now(UTC)
dt_mock.as_local = lambda dt: dt if dt.tzinfo else dt.replace(tzinfo=UTC)
dt_mock.start_of_local_day = lambda dt: (
    dt.replace(tzinfo=UTC)
    if isinstance(dt, datetime)
    else datetime.combine(dt, datetime.min.time(), tzinfo=UTC)
)
dt_mock.parse_datetime = lambda s: (
    datetime.fromisoformat(s.replace("Z", "+00:00"))
    if isinstance(s, str) and ("T" in s or " " in s)
    else None
)
dt_mock.parse_date = lambda s: (
    date.fromisoformat(s[:10]) if isinstance(s, str) and len(s) == 10 else None
)
sys.modules["homeassistant.util"].dt = dt_mock
sys.modules["homeassistant.util.dt"] = dt_mock


# Specific exceptions needed for inheritance
class ConfigEntryAuthFailed(Exception):
    pass


class ConfigEntryNotReady(Exception):
    pass


class UpdateFailed(Exception):
    pass


class HomeAssistantError(Exception):
    pass


sys.modules["homeassistant.exceptions"].ConfigEntryAuthFailed = ConfigEntryAuthFailed
sys.modules["homeassistant.exceptions"].ConfigEntryNotReady = ConfigEntryNotReady
sys.modules["homeassistant.exceptions"].HomeAssistantError = HomeAssistantError
sys.modules["homeassistant.helpers.update_coordinator"].UpdateFailed = UpdateFailed
sys.modules[
    "homeassistant.helpers.update_coordinator"
].CoordinatorEntity = CoordinatorEntity
sys.modules["homeassistant.components.calendar"].CalendarEntity = CalendarEntity
sys.modules["homeassistant.components.calendar"].CalendarEvent = CalendarEvent
sys.modules["homeassistant.components.sensor"].SensorEntity = SensorEntity
