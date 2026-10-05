"""DHL Tracking integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN, PLATFORMS
from .coordinator import DHLDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up DHL integration via YAML (not supported, UI only)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DHL Tracking from a config entry."""
    _LOGGER.debug("Setting up DHL Tracking entry: %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})

    coordinator = DHLDataUpdateCoordinator(hass, entry)

    # Restore cached shipment data to survive reboots without hitting the API
    await coordinator.async_load_cache()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    try:
        await coordinator.async_config_entry_first_refresh()
    except UpdateFailed as err:
        if not coordinator.data:
            raise ConfigEntryNotReady(f"Cannot initialize DHL tracking: {err}") from err
        _LOGGER.warning(
            "Initial DHL update failed, but serving cached tracking data. Error: %s",
            err,
        )

    # Listen for options flow updates (changing tracking numbers or interval)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    # Set up platforms (sensor, calendar)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload DHL config entry."""
    _LOGGER.debug("Unloading DHL entry: %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry after options change."""
    _LOGGER.debug(
        "Reloading DHL config entry due to updated options: %s", entry.entry_id
    )
    await hass.config_entries.async_reload(entry.entry_id)
