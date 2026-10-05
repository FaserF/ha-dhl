"""Constants for the DHL Tracking integration."""

from __future__ import annotations

DOMAIN = "dhl"
ATTRIBUTION = "Data provided by DHL Tracking"
PLATFORMS = ["sensor", "calendar"]

# Configuration keys
CONF_API_KEY = "api_key"
CONF_TRACKING_NUMBERS = "tracking_numbers"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_RECIPIENT_POSTAL_CODE = "recipient_postal_code"
CONF_ACCOUNT_MODE = "account_mode"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_AUTH_CODE = "auth_code"

# Account Mode options
ACCOUNT_MODE_NONE = "none"
ACCOUNT_MODE_TOKEN = "token"  # Recommended
ACCOUNT_MODE_WEB = "web"

# Defaults
DEFAULT_UPDATE_INTERVAL = 30  # minutes
MIN_UPDATE_INTERVAL = 10  # minutes
MAX_UPDATE_INTERVAL = 1440  # 24 hours

# API Configuration
DHL_PUBLIC_API_URL = "https://www.dhl.de/int-verfolgen/data/search"
DHL_OFFICIAL_API_BASE_URL = "https://api-eu.dhl.com/track/shipments"

# Anti-ban / Rate limiting defaults
DEFAULT_MIN_JITTER = 3.0  # seconds
DEFAULT_MAX_JITTER = 15.0  # seconds
DAILY_CALL_LIMIT = 240  # safety limit

# Issue IDs for HA Repairs
ISSUE_ID_AUTH = "auth_error"
ISSUE_ID_RATE_LIMIT = "rate_limit_exceeded"
ISSUE_ID_CONNECTION = "connection_error"
