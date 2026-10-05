"""Diagnostics support for DHL Tracking."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, CONF_AUTH_CODE, CONF_REFRESH_TOKEN, DOMAIN
from .coordinator import DHLDataUpdateCoordinator

TO_REDACT = {
    CONF_API_KEY,
    CONF_AUTH_CODE,
    CONF_REFRESH_TOKEN,
    "api_key",
    "password",
    "access_token",
    "refresh_token",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: DHLDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Redact sensitive shipment details if needed, e.g. exact delivery address lines
    shipments_data = {}
    if coordinator.data:
        for tracking_nr, data in coordinator.data.items():
            shipments_data[tracking_nr] = async_redact_data(data, TO_REDACT)

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
            "pref_disable_new_entities": entry.pref_disable_new_entities,
            "pref_disable_polling": entry.pref_disable_polling,
        },
        "coordinator": {
            "tracking_numbers_count": len(coordinator.tracking_numbers),
            "tracking_url": coordinator.tracking_url,
            "daily_calls_count": coordinator._daily_calls_count,
            "daily_calls_reset_date": coordinator._daily_calls_reset_date,
            "consecutive_failures": coordinator._consecutive_failures,
            "last_success": coordinator._last_success.isoformat()
            if coordinator._last_success
            else None,
            "backoff_until": coordinator._backoff_until.isoformat()
            if coordinator._backoff_until
            else None,
        },
        "shipments": shipments_data,
    }
