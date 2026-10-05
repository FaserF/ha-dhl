"""Calendar platform for DHL tracking."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, DOMAIN
from .coordinator import DHLDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _parse_datetime(dt_str: str | None) -> datetime | None:
    """Safely parse datetime string into timezone-aware datetime."""
    if not dt_str:
        return None
    try:
        parsed = dt_util.parse_datetime(dt_str)
        if parsed:
            if dt_util.as_local(parsed).tzinfo is None or parsed.tzinfo is None:
                return dt_util.as_utc(parsed)
            return parsed
        d = dt_util.parse_date(dt_str)
        if d:
            return dt_util.start_of_local_day(datetime.combine(d, datetime.min.time()))
    except Exception:
        pass
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DHL calendar entity from config entry."""
    coordinator: DHLDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([DHLTrackingCalendar(coordinator, entry)])


class DHLTrackingCalendar(CoordinatorEntity[DHLDataUpdateCoordinator], CalendarEntity):
    """Calendar entity containing events for all tracked DHL shipments."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_translation_key = "deliveries"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: DHLDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize DHL Calendar."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="DHL Tracking",
            manufacturer="DHL",
            model="Shipment Tracking API",
            configuration_url=coordinator.tracking_url,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming or current calendar event."""
        events = self._get_all_events()
        now = dt_util.now()
        upcoming = [e for e in events if self._event_end_dt(e) >= now]
        if upcoming:
            upcoming.sort(key=lambda x: self._event_start_dt(x))
            return upcoming[0]
        if events:
            return events[-1]
        return None

    @staticmethod
    def _event_start_dt(event: CalendarEvent) -> datetime:
        """Convert event start to timezone-aware datetime."""
        if isinstance(event.start, datetime):
            return dt_util.as_local(event.start)
        return dt_util.start_of_local_day(
            datetime.combine(event.start, datetime.min.time())
        )

    @staticmethod
    def _event_end_dt(event: CalendarEvent) -> datetime:
        """Convert event end to timezone-aware datetime."""
        if isinstance(event.end, datetime):
            return dt_util.as_local(event.end)
        return dt_util.start_of_local_day(
            datetime.combine(event.end, datetime.min.time())
        )

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a specific datetime range."""
        all_events = self._get_all_events()
        return [
            e
            for e in all_events
            if self._event_end_dt(e) >= start_date
            and self._event_start_dt(e) <= end_date
        ]

    def _get_all_events(self) -> list[CalendarEvent]:
        """Compile calendar events for all configured DHL tracking numbers."""
        events: list[CalendarEvent] = []
        if not self.coordinator.data:
            return events

        for tracking_number in self.coordinator.tracking_numbers:
            shipment = self.coordinator.data.get(tracking_number)
            if not shipment:
                continue

            summary = f"DHL Parcel {tracking_number}"
            status = shipment.get("status", {})
            desc = (
                status.get("description") or status.get("status") or "Parcel Delivery"
            )
            status_code = status.get("statusCode")

            est_str = shipment.get("estimatedTimeOfDelivery") or shipment.get(
                "estimatedDeliveryDate"
            )
            est_date = dt_util.parse_date(est_str) if est_str else None
            est_dt = dt_util.parse_datetime(est_str) if est_str else None

            if est_date and not est_dt:
                start = est_date
                end = est_date + timedelta(days=1)
            elif est_dt:
                if est_dt.tzinfo is None:
                    est_dt = dt_util.as_local(est_dt)
                start = est_dt
                end = est_dt + timedelta(hours=2)
            else:
                ts_str = status.get("timestamp")
                ts_dt = dt_util.parse_datetime(ts_str) if ts_str else None
                if ts_dt and ts_dt.tzinfo is None:
                    ts_dt = dt_util.as_local(ts_dt)
                start = ts_dt or dt_util.now()
                end = start + timedelta(hours=1)

            location = (
                status.get("location", {}).get("address", {}).get("addressLocality")
            )
            description_text = (
                f"Status: {desc}\nCode: {status_code}\nTracking: {tracking_number}"
            )

            events.append(
                CalendarEvent(
                    summary=summary,
                    start=start,
                    end=end,
                    description=description_text,
                    location=location,
                )
            )

        events.sort(key=lambda x: x.start)
        return events
