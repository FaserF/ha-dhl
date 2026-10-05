# DHL Tracking (for Home Assistant) 📦

[![GitHub Release](https://img.shields.io/github/release/FaserF/ha-dhl.svg?style=flat-square)](https://github.com/FaserF/ha-dhl/releases)
[![Downloads (Current release)](https://img.shields.io/github/downloads/FaserF/ha-dhl/latest/dhl.zip?label=Downloads%20(Current%20release)&style=flat-square)](https://github.com/FaserF/ha-dhl/releases)
[![License](https://img.shields.io/github/license/FaserF/ha-dhl.svg?style=flat-square)](LICENSE)
[![hacs](https://img.shields.io/badge/HACS-custom-orange.svg?style=flat-square)](https://hacs.xyz)
[![CI Orchestrator](https://github.com/FaserF/ha-dhl/actions/workflows/ci-orchestrator.yml/badge.svg)](https://github.com/FaserF/ha-dhl/actions/workflows/ci-orchestrator.yml)

A robust Home Assistant integration for tracking DHL parcels with **zero configuration required by default** (no API key needed for DHL Germany), plus optional support for the official global DHL Developer Portal API.

## 🧭 Quick Links

| | | | |
| :--- | :--- | :--- | :--- |
| [✨ Features](#-features) | [🌍 Supported Regions & Modes](#-supported-regions--operating-modes) | [🛡️ Anti-Ban Protections](#-anti-ban--rate-limiting-protections) | [📦 Installation](#-installation) |
| [⚙️ Configuration](#️-configuration) | [🔑 Getting an API Key](#-optional-getting-a-free-dhl-api-key) | [🔐 Login & Account Mode](#-login--account-mode-dhlr0--dhla0) | [🧑‍💻 Development](#-development) |

---

## ✨ Features

- **📅 Unified Calendar Entity (`calendar.dhl_deliveries`)**:
  - Aggregates **all** configured tracking numbers into a single calendar entity.
  - Automatically schedules estimated delivery dates (`estimatedTimeOfDelivery` / `estimatedDeliveryDate`) or latest milestone timestamps.
- **📦 Next Delivery Sensor (`sensor.dhl_next_delivery`)**:
  - Dynamically calculates the next incoming shipment based on delivery windows.
  - Comprehensive attributes: tracking number, status code, location, weight, product description, origin, destination city, milestone history, and your **Postnummer** (when account is connected).
- **🚚 Individual Parcel Sensors (`sensor.dhl_parcel_<number>`)**:
  - Dedicated sensor for every configured tracking number with full real-time event attributes.
- **⚡ Intuitive Configuration**:
  - Enter tracking numbers directly without an account, or link your DHL session token for authenticated tracking and Postnummer integration.
- **🚫 NO Fragile HTML Scraping**:
  - Uses official JSON endpoints (public `dhl.de` REST API or the developer portal API).

---

## 🌍 Supported Regions & Operating Modes

This integration offers two operating modes: **Keyless Public Mode (Default)** and **Official API Mode (Optional)**.

| Feature / Scope | 🆓 Keyless Mode (Default) | 🔑 Official API Mode (Optional) |
| :--- | :--- | :--- |
| **API Key Required** | ❌ **No** (Works out of the box) | ✅ **Yes** (Free from DHL Developer Portal) |
| **DHL Germany (DE) Domestic** | ✅ Full support | ✅ Full support |
| **Cross-border to/from Germany** | ✅ Full support (incoming & outgoing) | ✅ Full support |
| **Pure Domestic Foreign (e.g. NL to NL)** | ⚠️ Not supported (only parcels routed via DHL DE) | ✅ Full support worldwide |
| **DHL Express Worldwide** | ⚠️ Only if visible in DHL DE web tracking | ✅ Full global support |
| **DHL Freight & Global Forwarding** | ❌ Limited | ✅ Full support |
| **Daily Call Quota** | Guarded by internal anti-ban rate limiting | 250 free calls/day (developer portal tier) |

---

## 🔐 Login & Account Mode (`dhlr0` / `dhla0`)

### Cookies & Token Architecture

When you log into your DHL customer account at `dhl.de`, DHL's CIAM identity system creates two main tokens as browser cookies:

| Cookie | Type | Format | Lifetime | Purpose in Integration |
| :--- | :--- | :--- | :--- | :--- |
| **`dhlr0`** | Refresh Token | **JWE** (encrypted, 5 dot-separated parts) | ~7 days | Recommended for long-lived session cookie tracking. |
| **`dhla0`** | Access Token | **JWS** (signed, 3 dot-separated parts) | ~30 min | Contains readable payload claims, including your **`post_number`**! |

### ⚠️ Important API Limitations & Parcel Discovery

> [!IMPORTANT]
> **DHL does NOT provide a public REST API endpoint for automatically fetching your account's shipment list ("Meine Sendungen").**

During reverse-engineering of the DHL tracking single-page application (`/int-verfolgen/` and its bundles `main.*.js`, `ShipmentList.*.js`, `useNolpTheme.*.js`):
1. The shipment list in the browser is maintained inside **Magnolia CMS client-side storage** (`window.frontendSDK.storage`) and URL deep-link parameters (`verfolgenState`).
2. There is **no server-side REST endpoint** returning all user packages. Public search endpoints (`/int-verfolgen/data/search`) strictly require parcel codes passed via the `piececode` query parameter.
3. Protected CMS account endpoints (such as `/int-stammdaten/public/postnumber` or `/int-bonus/bonus/account-balance`) return `401 Unauthorized` without full Magnolia browser session headers.
4. **Consequently, tracking numbers must always be entered into the integration.** Automatic parcel sync directly from an account list is technically impossible without brittle headless browser automation.

### What Account Connection Provides

- **Authenticated Tracking Requests**: Injects `Cookie: dhlr0=...` (or `dhla0`) into tracking requests, preventing unauthenticated IP rate restrictions and accessing detailed tracking states.
- **Automatic Postnummer Extraction**: Providing `dhla0` (or entering it during setup/reauth) extracts your official DHL customer number (`post_number`) directly from the token payload and exposes it as an attribute on `sensor.dhl_next_delivery`.
- **Automatic Reauth Flow**: When tokens expire, Home Assistant creates a repair issue and initiates a reauth flow so you can update credentials smoothly without removing your entities.

### How to Retrieve Your Cookie (`dhlr0` or `dhla0`)

1. Open your browser and log into [dhl.de](https://www.dhl.de).
2. Press <kbd>F12</kbd> (or right click -> Inspect) to open **Developer Tools**.
3. Select the **Application** (Chrome/Edge) or **Storage** (Firefox) tab.
4. Expand **Cookies** in the left sidebar and select `https://www.dhl.de`.
5. Locate the cookie:
   - Copy **`dhlr0`** for a longer-lasting session (~7 days).
   - Alternatively copy **`dhla0`** to automatically extract and register your **Postnummer**.
6. Paste the entire string into the integration's token field.

---

## 🔑 (Optional) Getting a Free DHL API Key

You **do not need an API key** for standard DHL Germany parcel tracking. If you want global support for shipments outside Germany or across all international DHL divisions, you can obtain a free key:

1. Visit the [DHL API Developer Portal](https://developer.dhl.com/).
2. Create a free account (no business contract or customer number required).
3. In your dashboard, click **My Apps** > **Add App**.
4. Subscribe your app to the **Shipment Tracking - Unified** API (or **Post & Paket Deutschland Sendungsverfolgung**).
5. Copy your **API Key** (Consumer Key) and paste it into the integration configuration.

---

## 🛡️ Anti-Ban & Rate-Limiting Protections

To prevent rate limits and avoid blocks across both public and official endpoints:

1. **Random Jitter (3–15 s)**: Inserts an asynchronous delay between consecutive parcel requests to prevent burst spikes.
2. **Domain-Wide Concurrency Lock**: Serializes simultaneous polling cycles across multiple entries or during Home Assistant restarts.
3. **Daily Quota Safety Guard (240 calls/day)**: Automatically pauses scheduled polling before reaching the daily hard limit.
4. **Delivered Parcel Freezing**: Delivered shipments (`delivered`) are automatically skipped during routine background polling.
5. **Exponential Backoff**: Backs off for up to 24 hours upon encountering 429 (Rate Limit) or 403 responses.
6. **Restart Resistance**: Caches all shipment metadata and daily call counters in persistent HA Storage (`Store`), retaining states across reboots without re-querying the API.
7. **Graceful Fallback**: Retains cached parcel states if a momentary network error occurs.

---

## ❤️ Support This Project

<div align="center">

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor%20on-GitHub-%23EA4AAA?style=for-the-badge&logo=github-sponsors&logoColor=white)](https://github.com/sponsors/FaserF)&nbsp;&nbsp;
[![PayPal](https://img.shields.io/badge/Donate%20via-PayPal-%2300457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/FaserF)

</div>

---

## 📦 Installation

### HACS (Recommended)

1. Open **HACS** in Home Assistant.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Add `https://github.com/FaserF/ha-dhl` with category **Integration**.
4. Search for **DHL Tracking**, install the integration, and restart Home Assistant.

### Manual Installation

1. Download the latest `dhl.zip` release archive.
2. Extract the `custom_components/dhl` folder into your Home Assistant `custom_components/` directory.
3. Restart Home Assistant.

---

## ⚙️ Configuration

1. In Home Assistant, navigate to **Settings > Devices & Services > Add Integration**.
2. Search for **DHL**.
3. Choose your configuration mode:
   - **Keyless Public Tracking (Default)**: Enter tracking number(s) directly — no login required.
   - **DHL Account Connection (Optional)**:
     - **Option 1: Session / Refresh Token (`dhlr0` or `dhla0`)**:
       1. Follow the steps in [How to Retrieve Your Cookie](#how-to-retrieve-your-cookie-dhlr0-or-dhla0).
       2. Paste the token into the **Session Token** field.
       3. Enter your parcel tracking numbers in the tracking numbers field.
     - **Option 2: Web Auth / Authorization Code**:
       1. Follow the DHL browser authorization prompt.
       2. Complete login and 2FA verification.
       3. Copy the `code` parameter from the redirect address bar URL into Home Assistant.
4. *(Optional)* Enter a DHL Developer Portal API key for official global API coverage.
5. *(Optional)* Enter a recipient postal code for enhanced destination matching.

> [!TIP]
> You can update your tracking numbers or switch connection modes at any time in **Settings > Devices & Services > DHL > Configure (Options)**.

---

## 🧑‍💻 Development

```bash
# Run tests (Linux / WSL required — pytest-homeassistant uses Linux-only fcntl)
pytest

# Lint
ruff check . --fix

# Format
ruff format .

# Type check
mypy --ignore-missing-imports --follow-imports=skip custom_components/dhl
```

---

## 📄 License

This project is licensed under the MIT License.
