"""DHL Tracking API Client supporting both public web endpoint and Developer Portal API."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import aiohttp

from .const import DHL_OFFICIAL_API_BASE_URL, DHL_PUBLIC_API_URL

_LOGGER = logging.getLogger(__name__)


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode unencrypted JWT/JWS claims without external cryptography dependencies.

    Tokens with 3 parts (JWS, e.g. dhla0) contain readable payload claims like
    post_number, display_name, email, exp, etc.
    Encrypted JWE tokens (5 parts, e.g. dhlr0) return empty claims dictionary.
    """
    clean = token.strip()
    parts = clean.split(".")
    if len(parts) != 3:
        return {}
    try:
        payload = parts[1]
        padded = payload + "=" * ((4 - len(payload) % 4) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        data = json.loads(decoded.decode("utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as err:
        _LOGGER.debug("Failed to decode token payload: %s", err)
    return {}


class DHLAPIError(Exception):
    """Base exception for DHL API errors."""


class DHLAuthError(DHLAPIError):
    """Authentication or authorization failed (401, 403)."""


class DHLRateLimitError(DHLAPIError):
    """Rate limit exceeded (429)."""


class DHLNotFoundError(DHLAPIError):
    """Shipment not found (404)."""


class DHLAPIClient:
    """Async API Client for DHL Shipment Tracking (Keyless public or Official API)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str | None = None,
        refresh_token: str | None = None,
        auth_code: str | None = None,
    ) -> None:
        """Initialize DHL API Client."""
        self._session = session
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self._refresh_token = (
            refresh_token.strip() if refresh_token and refresh_token.strip() else None
        )
        self._auth_code = auth_code.strip() if auth_code and auth_code.strip() else None

    async def validate_token(self, token: str) -> bool:
        """Validate an entered JWT/JWE cookie and test connectivity with DHL.

        DHL's dhlr0 cookie is a JWE (JSON Web Encryption) with 5 dot-separated
        parts (header.key.iv.ciphertext.tag). Classic JWS tokens have 3 parts.
        Both formats are accepted here.
        """
        clean = token.strip()
        if not clean or len(clean) < 20:
            raise DHLAuthError("Token is too short or empty")
        # Accept JWS (3 parts) and JWE (5 parts) — dhlr0 is a JWE.
        parts = clean.split(".")
        if len(parts) not in (3, 5):
            raise DHLAuthError(
                "Token is not a valid JWT/JWE (expected 3 or 5 dot-separated parts)"
            )

        # A 200 response (even with empty sendungen) confirms the token is accepted.
        # 401/403 means DHL rejected it.
        test_url = "https://www.dhl.de/int-verfolgen/data/search"
        cookie_header = (
            f"dhlr0={clean}" if len(parts) == 5 else f"dhla0={clean}; dhlr0={clean}"
        )
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Cookie": cookie_header,
        }
        try:
            async with self._session.get(
                test_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status in (401, 403):
                    raise DHLAuthError(
                        f"DHL rejected authentication token (HTTP {response.status})"
                    )
                if response.status == 429:
                    raise DHLRateLimitError(
                        "DHL rate limit encountered while testing token"
                    )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise DHLAPIError(f"Network error testing token with DHL: {err}") from err

        return True

    async def get_shipment(
        self,
        tracking_number: str,
        recipient_postal_code: str | None = None,
        language: str = "de",
    ) -> dict[str, Any] | None:
        """Fetch tracking data for a single shipment.

        If api_key is present, queries official API.
        Otherwise, queries the public DHL web tracking endpoint without any key.
        """
        clean_tracking = tracking_number.strip()
        if self._api_key:
            return await self._get_shipment_official(
                clean_tracking, recipient_postal_code, language
            )
        return await self._get_shipment_public(clean_tracking, language)

    async def _get_shipment_public(
        self,
        tracking_number: str,
        language: str = "de",
    ) -> dict[str, Any] | None:
        """Fetch tracking data via public DHL tracking JSON endpoint (no API key required)."""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        if self._refresh_token:
            parts = self._refresh_token.split(".")
            if len(parts) == 3:
                headers["Cookie"] = (
                    f"dhla0={self._refresh_token}; dhlr0={self._refresh_token}"
                )
            else:
                headers["Cookie"] = f"dhlr0={self._refresh_token}"
        params = {
            "piececode": tracking_number,
            "language": language,
        }

        _LOGGER.debug("Requesting public DHL tracking data for %s", tracking_number)

        try:
            async with self._session.get(
                DHL_PUBLIC_API_URL,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                status = response.status

                if status == 429:
                    raise DHLRateLimitError(
                        "DHL public tracking rate limit exceeded (429)"
                    )

                if status != 200:
                    text = await response.text()
                    raise DHLAPIError(
                        f"DHL public endpoint returned HTTP {status}: {text}"
                    )

                data = await response.json()

                if data.get("rateLimited"):
                    raise DHLRateLimitError(
                        "DHL public response flagged as rate limited"
                    )

                sendungen = data.get("sendungen", [])
                if not sendungen:
                    return None

                raw = sendungen[0]
                if not raw.get("hasCompleteDetails") and not raw.get("sendungsdetails"):
                    return None

                return self._normalize_public_response(raw)

        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning("Network error contacting DHL public tracking: %s", err)
            raise DHLAPIError(f"Network error contacting DHL: {err}") from err

    async def _get_shipment_official(
        self,
        tracking_number: str,
        recipient_postal_code: str | None = None,
        language: str = "de",
    ) -> dict[str, Any] | None:
        """Fetch tracking data via official DHL Developer Portal API."""
        headers = {
            "Accept": "application/json",
            "DHL-API-Key": self._api_key or "",
            "User-Agent": "HomeAssistant-DHL-Tracking/0.1.0",
        }
        params: dict[str, str] = {
            "trackingNumber": tracking_number,
            "language": language,
        }
        if recipient_postal_code and recipient_postal_code.strip():
            params["recipientPostalCode"] = recipient_postal_code.strip()

        try:
            async with self._session.get(
                DHL_OFFICIAL_API_BASE_URL,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=25),
            ) as response:
                status = response.status

                if status in (401, 403):
                    text = await response.text()
                    raise DHLAuthError(f"DHL Authentication Failed ({status}): {text}")

                if status == 429:
                    raise DHLRateLimitError("DHL rate limit exceeded (429)")

                if status == 404:
                    return None

                if status != 200:
                    text = await response.text()
                    raise DHLAPIError(f"DHL API returned HTTP {status}: {text}")

                data = await response.json()
                shipments = data.get("shipments", [])
                return shipments[0] if shipments else None

        except (aiohttp.ClientError, TimeoutError) as err:
            raise DHLAPIError(f"Network error contacting DHL API: {err}") from err

    def _normalize_public_response(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize public dhl.de response into unified schema."""
        details = raw.get("sendungsdetails", {})
        verlauf = details.get("sendungsverlauf", {})
        zustellung = details.get("zustellung", {})

        events = []
        for ev in verlauf.get("events", []):
            events.append(
                {
                    "timestamp": ev.get("datum"),
                    "statusCode": "in_transit",
                    "description": ev.get("status"),
                }
            )

        # Calculate estimated delivery date from delivery window
        est_delivery_date = zustellung.get("zustellzeitfensterBis") or zustellung.get(
            "zustellzeitfensterVon"
        )

        return {
            "id": raw.get("id"),
            "service": "DHL Paket",
            "status": {
                "statusCode": "delivered"
                if details.get("istZugestellt")
                else "in_transit",
                "status": verlauf.get("status"),
                "description": verlauf.get("status"),
                "timestamp": verlauf.get("datumAktuellerStatus"),
            },
            "estimatedDeliveryDate": est_delivery_date,
            "estimatedTimeOfDelivery": None,
            "details": {
                "product": {
                    "productName": "Express"
                    if details.get("expressSendung")
                    else "DHL Paket",
                },
                "totalNumberOfPieces": 1,
            },
            "destination": {
                "address": {
                    "countryCode": details.get("zielland"),
                }
            },
            "events": events,
            "is_delivered": details.get("istZugestellt", False),
            "progress_step": verlauf.get("fortschritt"),
            "progress_max": verlauf.get("maximalFortschritt"),
        }
