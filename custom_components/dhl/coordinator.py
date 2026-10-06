"""Data Update Coordinator for the DHL Tracking integration.

Anti-ban & reliability strategies:
- Random jitter delay (3–15 s) between requests to avoid burst rate-limiting
- Domain-wide asyncio.Lock to serialise concurrent fetches
- Daily request counter with safety limits (max 240 reqs/day)
- Exponential backoff on 429/403 (up to 24h)
- Restart-resistance: last success & shipment states persisted via HA Storage
- Graceful degradation: keeps existing tracking cache alive on intermittent failures
- Auto-pause when shipments are delivered to prevent wasting API quota
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import storage
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import DHLAPIClient, DHLAuthError, DHLRateLimitError, decode_jwt_payload
from .const import (
    CONF_API_KEY,
    CONF_AUTH_CODE,
    CONF_AUTO_PRUNE_DAYS,
    CONF_AUTO_PRUNE_DELIVERED,
    CONF_RECIPIENT_POSTAL_CODE,
    CONF_REFRESH_TOKEN,
    CONF_TRACKING_NUMBERS,
    CONF_UPDATE_INTERVAL,
    DAILY_CALL_LIMIT,
    DEFAULT_AUTO_PRUNE_DAYS,
    DEFAULT_AUTO_PRUNE_DELIVERED,
    DEFAULT_MAX_JITTER,
    DEFAULT_MIN_JITTER,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    ISSUE_ID_AUTH,
    ISSUE_ID_CONNECTION,
    ISSUE_ID_RATE_LIMIT,
    MIN_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class DHLDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manage fetching DHL tracking data."""

    config_entry: config_entries.ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: config_entries.ConfigEntry,
    ) -> None:
        """Initialize DHL coordinator."""
        self.config_entry = entry
        config = {**entry.data, **entry.options}

        self.api_key: str | None = config.get(CONF_API_KEY) or None
        raw_tracking = config.get(CONF_TRACKING_NUMBERS, [])
        if isinstance(raw_tracking, str):
            self.tracking_numbers = [
                n.strip() for n in raw_tracking.split(",") if n.strip()
            ]
        else:
            self.tracking_numbers = [
                str(n).strip() for n in raw_tracking if str(n).strip()
            ]

        self.recipient_postal_code: str | None = config.get(CONF_RECIPIENT_POSTAL_CODE)
        self.refresh_token: str | None = config.get(CONF_REFRESH_TOKEN)
        self.auth_code: str | None = config.get(CONF_AUTH_CODE)

        # Extract account claims if unencrypted token (e.g. dhla0 or entry data claims)
        self.account_claims: dict[str, Any] = {}
        if self.refresh_token:
            self.account_claims = decode_jwt_payload(self.refresh_token)
        stored_claims = config.get("account_claims")
        if isinstance(stored_claims, dict):
            self.account_claims = {**stored_claims, **self.account_claims}

        self.post_number: str | None = self.account_claims.get(
            "post_number"
        ) or config.get("post_number")

        interval_minutes = max(
            MIN_UPDATE_INTERVAL,
            config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )

        session = async_get_clientsession(hass)
        self.client = DHLAPIClient(
            session=session,
            api_key=self.api_key,
            refresh_token=self.refresh_token,
            auth_code=self.auth_code,
        )

        self.auto_prune_delivered: bool = bool(
            config.get(CONF_AUTO_PRUNE_DELIVERED, DEFAULT_AUTO_PRUNE_DELIVERED)
        )
        self.auto_prune_days: int = int(
            config.get(CONF_AUTO_PRUNE_DAYS, DEFAULT_AUTO_PRUNE_DAYS)
        )

        # Delivered timestamps per tracking number for auto-pruning
        self.delivered_dates: dict[str, str] = {}

        # Anti-ban / Rate-limit state
        self._backoff_until: datetime | None = None
        self._consecutive_failures: int = 0
        self._last_success: datetime | None = None
        self._force_update: bool = False
        self._daily_calls_count: int = 0
        self._daily_calls_reset_date: str = dt_util.now().strftime("%Y-%m-%d")

        # HA persistent storage for restart-resistance
        self.store = storage.Store(hass, 1, f"{DOMAIN}_{entry.entry_id}")

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="DHL Tracking",
            update_interval=timedelta(minutes=interval_minutes),
        )

    @property
    def tracking_url(self) -> str:
        """Return DHL web tracking URL, pointing to shipment if single tracking number."""
        base_url = "https://www.dhl.de/de/privatkunden/dhl-sendungsverfolgung.html"
        if len(self.tracking_numbers) == 1:
            return f"{base_url}?piececode={self.tracking_numbers[0]}"
        return base_url

    async def async_load_cache(self) -> None:
        """Load cached shipment data from HA storage (restart-resistance)."""
        _LOGGER.debug("Loading cached DHL data for %s", self.config_entry.entry_id)
        cache = await self.store.async_load()
        if cache and isinstance(cache, dict):
            self.data = cache.get("shipments_data", {})
            last_success_str = cache.get("last_success")
            if last_success_str:
                try:
                    self._last_success = dt_util.parse_datetime(last_success_str)
                except (ValueError, TypeError):
                    self._last_success = None

            self._daily_calls_count = cache.get("daily_calls_count", 0)
            self._daily_calls_reset_date = cache.get(
                "daily_calls_reset_date", dt_util.now().strftime("%Y-%m-%d")
            )
            raw_delivered = cache.get("delivered_dates")
            if isinstance(raw_delivered, dict):
                self.delivered_dates = {
                    str(k): str(v) for k, v in raw_delivered.items()
                }
            _LOGGER.debug(
                "Restored %d DHL shipment records and %d delivery dates from persistent storage",
                len(self.data),
                len(self.delivered_dates),
            )

    def _check_daily_quota(self) -> bool:
        """Check and update daily API call quota."""
        today = dt_util.now().strftime("%Y-%m-%d")
        if self._daily_calls_reset_date != today:
            self._daily_calls_reset_date = today
            self._daily_calls_count = 0

        if self._daily_calls_count >= DAILY_CALL_LIMIT:
            _LOGGER.warning(
                "DHL Daily call limit reached (%d/%d). Skipping further API calls until tomorrow.",
                self._daily_calls_count,
                DAILY_CALL_LIMIT,
            )
            return False
        return True

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch tracking data for all configured numbers with anti-ban logic."""
        _LOGGER.debug("Starting DHL update cycle (force_update=%s)", self._force_update)

        if (
            not self._force_update
            and self._backoff_until
            and dt_util.now() < self._backoff_until
        ):
            _LOGGER.warning(
                "Skipping DHL update: backoff active until %s",
                self._backoff_until,
            )
            if self.data:
                return self.data
            raise UpdateFailed(
                f"DHL API update blocked by backoff until {self._backoff_until}"
            )

        if not self._force_update and not self._check_daily_quota():
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_ID_RATE_LIMIT,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="daily_limit_reached",
            )
            if self.data:
                return self.data
            raise UpdateFailed("Daily DHL API quota exhausted")

        domain_data = self.hass.data.setdefault(DOMAIN, {})
        fetch_lock: asyncio.Lock = domain_data.setdefault("fetch_lock", asyncio.Lock())

        updated_shipments: dict[str, Any] = dict(self.data or {})

        async with fetch_lock:
            for idx, tracking_number in enumerate(self.tracking_numbers):
                clean_nr = tracking_number.strip()
                if not clean_nr:
                    continue

                existing = updated_shipments.get(clean_nr)
                if (
                    not self._force_update
                    and existing
                    and existing.get("status", {}).get("statusCode") == "delivered"
                ):
                    _LOGGER.debug(
                        "Shipment %s is already marked delivered. Skipping fetch.",
                        clean_nr,
                    )
                    continue

                if idx > 0 and not self._force_update:
                    jitter = random.uniform(DEFAULT_MIN_JITTER, DEFAULT_MAX_JITTER)
                    _LOGGER.debug(
                        "Waiting %.1f s jitter before next parcel check", jitter
                    )
                    await asyncio.sleep(jitter)

                try:
                    shipment = await self.client.get_shipment(
                        clean_nr,
                        recipient_postal_code=self.recipient_postal_code,
                    )
                    self._daily_calls_count += 1
                    if shipment:
                        updated_shipments[clean_nr] = shipment
                        if shipment.get("status", {}).get("statusCode") == "delivered":
                            if clean_nr not in self.delivered_dates:
                                self.delivered_dates[clean_nr] = (
                                    dt_util.now().isoformat()
                                )
                    else:
                        updated_shipments[clean_nr] = {
                            "id": clean_nr,
                            "status": {
                                "statusCode": "not_found",
                                "status": "Not found",
                                "description": "No shipment data available",
                            },
                        }
                except DHLAuthError as auth_err:
                    _LOGGER.error("DHL Auth Error for %s: %s", clean_nr, auth_err)
                    self.config_entry.async_start_reauth(self.hass)
                    ir.async_create_issue(
                        self.hass,
                        DOMAIN,
                        ISSUE_ID_AUTH,
                        is_fixable=False,
                        severity=ir.IssueSeverity.ERROR,
                        translation_key="auth_error",
                    )
                    raise UpdateFailed(
                        f"DHL Authentication error: {auth_err}"
                    ) from auth_err
                except DHLRateLimitError as rate_err:
                    self._consecutive_failures += 1
                    backoff_hours = min(24, self._consecutive_failures * 2)
                    self._backoff_until = dt_util.now() + timedelta(hours=backoff_hours)
                    _LOGGER.warning(
                        "DHL 429 rate limit encountered. Backing off for %d hours.",
                        backoff_hours,
                    )
                    ir.async_create_issue(
                        self.hass,
                        DOMAIN,
                        ISSUE_ID_RATE_LIMIT,
                        is_fixable=False,
                        severity=ir.IssueSeverity.WARNING,
                        translation_key="rate_limit_exceeded",
                    )
                    if self.data:
                        return self.data
                    raise UpdateFailed("DHL 429 Rate limit exceeded") from rate_err
                except Exception as err:
                    self._consecutive_failures += 1
                    _LOGGER.warning(
                        "Error fetching DHL tracking for %s: %s", clean_nr, err
                    )
                    if self.data:
                        return self.data
                    raise UpdateFailed(
                        f"Error fetching DHL shipment {clean_nr}: {err}"
                    ) from err

            # Check for delivered parcels and register delivery date if already marked delivered
            for nr in self.tracking_numbers:
                c_nr = nr.strip()
                if (
                    c_nr in updated_shipments
                    and updated_shipments[c_nr].get("status", {}).get("statusCode")
                    == "delivered"
                    and c_nr not in self.delivered_dates
                ):
                    status_ts = (
                        updated_shipments[c_nr].get("status", {}).get("timestamp")
                    )
                    parsed_ts = dt_util.parse_datetime(status_ts) if status_ts else None
                    self.delivered_dates[c_nr] = (
                        parsed_ts.isoformat()
                        if parsed_ts
                        else dt_util.now().isoformat()
                    )

            # Auto-prune delivered shipments older than auto_prune_days
            if self.auto_prune_delivered and self.auto_prune_days > 0:
                cutoff = dt_util.now() - timedelta(days=self.auto_prune_days)
                to_remove: list[str] = []

                for nr in list(self.tracking_numbers):
                    c_nr = nr.strip()
                    deliv_str = self.delivered_dates.get(c_nr)
                    if not deliv_str:
                        continue
                    deliv_dt = dt_util.parse_datetime(deliv_str)
                    if deliv_dt and deliv_dt <= cutoff:
                        to_remove.append(c_nr)

                if to_remove:
                    _LOGGER.info(
                        "Auto-pruning %d delivered DHL shipments older than %d days: %s",
                        len(to_remove),
                        self.auto_prune_days,
                        to_remove,
                    )
                    new_tracking = [
                        n for n in self.tracking_numbers if n.strip() not in to_remove
                    ]
                    self.tracking_numbers = new_tracking
                    for r_nr in to_remove:
                        updated_shipments.pop(r_nr, None)
                        self.delivered_dates.pop(r_nr, None)

                    # Update config entry asynchronously without triggering immediate reload
                    new_data = dict(self.config_entry.data)
                    new_data[CONF_TRACKING_NUMBERS] = new_tracking
                    new_options = dict(self.config_entry.options)
                    if CONF_TRACKING_NUMBERS in new_options:
                        new_options[CONF_TRACKING_NUMBERS] = new_tracking

                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data=new_data,
                        options=new_options,
                    )

        self._last_success = dt_util.now()
        self._consecutive_failures = 0
        self._force_update = False

        ir.async_delete_issue(self.hass, DOMAIN, ISSUE_ID_CONNECTION)
        ir.async_delete_issue(self.hass, DOMAIN, ISSUE_ID_AUTH)

        await self.store.async_save(
            {
                "shipments_data": updated_shipments,
                "last_success": self._last_success.isoformat(),
                "daily_calls_count": self._daily_calls_count,
                "daily_calls_reset_date": self._daily_calls_reset_date,
                "delivered_dates": self.delivered_dates,
            }
        )

        return updated_shipments
