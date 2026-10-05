"""Sensor platform for DHL tracking."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, DOMAIN
from .coordinator import DHLDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _parse_event_datetime(timestamp_str: str | None) -> datetime | None:
    """Parse ISO timestamp safely."""
    if not timestamp_str:
        return None
    try:
        parsed = dt_util.parse_datetime(timestamp_str)
        if parsed:
            return parsed
    except Exception:
        pass
    return None


def _extract_shipment_attributes(shipment: dict[str, Any]) -> dict[str, Any]:
    """Extract all available fields and metadata from the DHL API shipment model."""
    status = shipment.get("status", {})
    status_loc = status.get("location", {}).get("address", {})
    events = shipment.get("events", [])
    last_event = events[0] if events else {}
    last_event_loc = last_event.get("location", {}).get("address", {})
    details = shipment.get("details", {})
    dimensions = details.get("dimensions", {})
    weight = details.get("weight", {})
    product = details.get("product", {})
    origin = shipment.get("origin", {}).get("address", {})
    dest = shipment.get("destination", {}).get("address", {})
    pod = shipment.get("proofOfDelivery", {})
    pod_doc = pod.get("documentUrl") or pod.get("documentURL")

    attrs: dict[str, Any] = {
        "tracking_number": shipment.get("id"),
        "service": shipment.get("service"),
        "status_code": status.get("statusCode"),
        "status_description": status.get("description") or status.get("status"),
        "status_timestamp": status.get("timestamp"),
        "status_remark": status.get("remark"),
        "status_location": status_loc.get("addressLocality"),
        "status_postal_code": status_loc.get("postalCode"),
        "status_country": status_loc.get("countryCode"),
        "estimated_delivery": (
            shipment.get("estimatedTimeOfDelivery")
            or shipment.get("estimatedDeliveryDate")
        ),
        "estimated_delivery_remark": shipment.get("estimatedTimeOfDeliveryRemark"),
        "service_url": shipment.get("serviceUrl"),
        "reroute_url": shipment.get("rerouteUrl"),
        "product_name": product.get("productName"),
        "total_pieces": details.get("totalNumberOfPieces"),
        "piece_ids": details.get("pieceIds"),
        "weight": weight.get("value"),
        "weight_unit": weight.get("unitText"),
        "dimensions": (
            f"{dimensions.get('length')}x{dimensions.get('width')}x{dimensions.get('height')} {dimensions.get('unitText')}"
            if dimensions.get("length")
            else None
        ),
        "origin_city": origin.get("addressLocality"),
        "origin_country": origin.get("countryCode"),
        "destination_city": dest.get("addressLocality"),
        "destination_country": dest.get("countryCode"),
        "proof_of_delivery_signed_by": pod.get("signedBy"),
        "proof_of_delivery_timestamp": pod.get("timestamp"),
        "proof_of_delivery_document_url": pod_doc,
        "last_event_description": last_event.get("description")
        or last_event.get("statusCode"),
        "last_event_timestamp": last_event.get("timestamp"),
        "last_event_location": last_event_loc.get("addressLocality"),
        "events_count": len(events),
        "events_history": [
            {
                "timestamp": ev.get("timestamp"),
                "status_code": ev.get("statusCode"),
                "description": ev.get("description") or ev.get("status"),
                "location": ev.get("location", {})
                .get("address", {})
                .get("addressLocality"),
            }
            for ev in events[:10]
        ],
    }
    # Clean None values where appropriate while keeping explicit schema
    return {k: v for k, v in attrs.items() if v is not None}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DHL sensors from a config entry."""
    coordinator: DHLDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        DHLNextDeliverySensor(coordinator, entry),
    ]

    known_tracking_numbers: set[str] = set()

    for tracking_number in coordinator.tracking_numbers:
        known_tracking_numbers.add(tracking_number)
        entities.append(DHLParcelSensor(coordinator, entry, tracking_number))

    async_add_entities(entities)

    # Listen for dynamically added tracking numbers or discovered shipments
    def _async_check_new_shipments() -> None:
        new_entities: list[SensorEntity] = []
        all_numbers = set(coordinator.tracking_numbers) | set(
            coordinator.data.keys() if coordinator.data else []
        )
        for nr in all_numbers:
            if nr and nr not in known_tracking_numbers:
                known_tracking_numbers.add(nr)
                new_entities.append(DHLParcelSensor(coordinator, entry, nr))
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_async_check_new_shipments))


class DHLNextDeliverySensor(CoordinatorEntity[DHLDataUpdateCoordinator], SensorEntity):
    """Sensor that displays the next upcoming delivery date and parcel details."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_translation_key = "next_delivery"
    _attr_icon = "mdi:package-variant-closed"

    def __init__(
        self,
        coordinator: DHLDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize next delivery sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_next_delivery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="DHL Tracking",
            manufacturer="DHL",
            model="Shipment Tracking API",
            configuration_url=coordinator.tracking_url,
        )

    @property
    def native_value(self) -> str | None:
        """Return the next delivery date or status."""
        next_parcel = self._get_next_parcel()
        if not next_parcel:
            return "No active shipments"

        est_time = next_parcel.get("estimatedTimeOfDelivery")
        if est_time:
            dt = _parse_event_datetime(est_time)
            if dt:
                return dt.strftime("%Y-%m-%d %H:%M")
            return str(est_time)

        est_date = next_parcel.get("estimatedDeliveryDate")
        if est_date:
            return str(est_date)

        status = next_parcel.get("status", {})
        return status.get("description") or status.get("status") or "In transit"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all relevant information of the next parcel as attributes."""
        next_parcel = self._get_next_parcel()
        if not next_parcel:
            attrs: dict[str, Any] = {
                "active_shipments_count": 0,
                "total_tracked_shipments": len(self.coordinator.tracking_numbers),
            }
            if self.coordinator.post_number:
                attrs["post_number"] = self.coordinator.post_number
            return attrs

        attrs = _extract_shipment_attributes(next_parcel)
        attrs["total_tracked_shipments"] = len(self.coordinator.tracking_numbers)
        if self.coordinator.post_number:
            attrs["post_number"] = self.coordinator.post_number
        return attrs

    def _get_next_parcel(self) -> dict[str, Any] | None:
        """Find the parcel with the earliest upcoming delivery date or active transit."""
        if not self.coordinator.data:
            return None

        candidates: list[tuple[datetime | None, dict[str, Any]]] = []
        for tracking_nr in self.coordinator.tracking_numbers:
            shipment = self.coordinator.data.get(tracking_nr)
            if not shipment:
                continue
            status_code = shipment.get("status", {}).get("statusCode")
            if status_code == "delivered":
                continue

            est_str = shipment.get("estimatedTimeOfDelivery") or shipment.get(
                "estimatedDeliveryDate"
            )
            est_dt = _parse_event_datetime(est_str) if est_str else None
            candidates.append((est_dt, shipment))

        if not candidates:
            first_key = (
                self.coordinator.tracking_numbers[0]
                if self.coordinator.tracking_numbers
                else None
            )
            return self.coordinator.data.get(first_key) if first_key else None

        with_dt: list[tuple[datetime, dict[str, Any]]] = [
            (c[0], c[1]) for c in candidates if c[0] is not None
        ]
        without_dt = [c for c in candidates if c[0] is None]

        if with_dt:
            with_dt.sort(key=lambda x: x[0])
            return with_dt[0][1]

        return without_dt[0][1]


class DHLParcelSensor(CoordinatorEntity[DHLDataUpdateCoordinator], SensorEntity):
    """Sensor for an individual DHL parcel tracking number."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_icon = "mdi:truck-delivery"

    def __init__(
        self,
        coordinator: DHLDataUpdateCoordinator,
        entry: ConfigEntry,
        tracking_number: str,
    ) -> None:
        """Initialize single parcel sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self.tracking_number = tracking_number
        self._attr_unique_id = f"{entry.entry_id}_parcel_{tracking_number}"
        self._attr_name = f"Parcel {tracking_number}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="DHL Tracking",
            manufacturer="DHL",
            model="Shipment Tracking API",
            configuration_url=coordinator.tracking_url,
        )

    @property
    def native_value(self) -> str:
        """Return current status description."""
        shipment = (self.coordinator.data or {}).get(self.tracking_number)
        if not shipment:
            return "Unknown"
        status = shipment.get("status", {})
        return status.get("description") or status.get("status") or "Unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of this parcel."""
        shipment = (self.coordinator.data or {}).get(self.tracking_number)
        if not shipment:
            return {"tracking_number": self.tracking_number}

        return _extract_shipment_attributes(shipment)
