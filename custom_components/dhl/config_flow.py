"""Config flow and Options flow for DHL Tracking integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DHLAPIClient, DHLAuthError, DHLRateLimitError, decode_jwt_payload
from .const import (
    ACCOUNT_MODE_NONE,
    ACCOUNT_MODE_TOKEN,
    ACCOUNT_MODE_WEB,
    CONF_ACCOUNT_MODE,
    CONF_API_KEY,
    CONF_AUTH_CODE,
    CONF_RECIPIENT_POSTAL_CODE,
    CONF_REFRESH_TOKEN,
    CONF_TRACKING_NUMBERS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


def _clean_tracking_list(raw_input: Any) -> list[str]:
    """Clean and parse comma or line separated tracking numbers."""
    if isinstance(raw_input, list):
        return [str(item).strip() for item in raw_input if str(item).strip()]
    if isinstance(raw_input, str):
        items = raw_input.replace("\n", ",").split(",")
        return [item.strip() for item in items if item.strip()]
    return []


class DHLConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DHL Tracking."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize DHL config flow."""
        super().__init__()
        self._user_input_data: dict[str, Any] = {}

    @classmethod
    @callback
    def async_get_options_flow(
        cls,
        config_entry: config_entries.ConfigEntry,
    ) -> DHLOptionsFlowHandler:
        """Get the options flow for this handler."""
        return DHLOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial user setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip() or None
            tracking_list = _clean_tracking_list(
                user_input.get(CONF_TRACKING_NUMBERS, "")
            )
            postal_code = user_input.get(CONF_RECIPIENT_POSTAL_CODE, "").strip() or None
            account_mode = user_input.get(CONF_ACCOUNT_MODE, ACCOUNT_MODE_NONE)
            refresh_token = user_input.get(CONF_REFRESH_TOKEN, "").strip()
            auth_code = user_input.get(CONF_AUTH_CODE, "").strip()

            if not tracking_list and account_mode == ACCOUNT_MODE_NONE:
                errors[CONF_TRACKING_NUMBERS] = "empty_tracking_numbers"
            elif account_mode == ACCOUNT_MODE_TOKEN and not refresh_token:
                errors[CONF_REFRESH_TOKEN] = "empty_token"
            elif account_mode == ACCOUNT_MODE_WEB and not auth_code:
                errors[CONF_AUTH_CODE] = "empty_code"
            else:
                session = async_get_clientsession(self.hass)

                # Validate account token if supplied
                if account_mode == ACCOUNT_MODE_TOKEN and refresh_token:
                    client = DHLAPIClient(session=session)
                    try:
                        await client.validate_token(refresh_token)
                    except DHLAuthError:
                        errors[CONF_REFRESH_TOKEN] = "empty_token"
                    except Exception as err:
                        _LOGGER.warning("DHL token validation error: %s", err)
                        errors["base"] = "cannot_connect"

                # Validate sample tracking number if provided
                if not errors and tracking_list:
                    client = DHLAPIClient(
                        session=session,
                        api_key=api_key,
                        refresh_token=refresh_token or None,
                    )
                    test_number = tracking_list[0]
                    try:
                        await client.get_shipment(
                            test_number, recipient_postal_code=postal_code
                        )
                    except DHLAuthError:
                        errors["base"] = "invalid_auth"
                    except DHLRateLimitError:
                        errors["base"] = "rate_limit"
                    except Exception as err:
                        _LOGGER.warning("DHL test request error: %s", err)
                        errors["base"] = "cannot_connect"

                if not errors:
                    claims = decode_jwt_payload(refresh_token) if refresh_token else {}
                    post_number = claims.get("post_number")

                    self._user_input_data = {
                        CONF_API_KEY: api_key or "",
                        CONF_TRACKING_NUMBERS: tracking_list,
                        CONF_RECIPIENT_POSTAL_CODE: postal_code,
                        CONF_ACCOUNT_MODE: account_mode,
                        CONF_REFRESH_TOKEN: refresh_token,
                        CONF_AUTH_CODE: auth_code,
                        CONF_UPDATE_INTERVAL: user_input.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                        "account_claims": claims,
                        "post_number": post_number,
                    }

                    if account_mode == ACCOUNT_MODE_TOKEN and refresh_token:
                        unique_id = (
                            f"account_{post_number}"
                            if post_number
                            else f"account_{refresh_token[:10]}"
                        )
                        title = (
                            f"DHL Account {post_number} ({len(tracking_list)} shipments)"
                            if post_number
                            else f"DHL Account ({len(tracking_list)} shipments)"
                        )
                    elif account_mode == ACCOUNT_MODE_WEB and auth_code:
                        unique_id = f"web_{auth_code[:10]}"
                        title = f"DHL Account Web ({len(tracking_list)} shipments)"
                    else:
                        unique_id = (
                            api_key[:12]
                            if api_key
                            else (
                                f"public_{tracking_list[0][:10]}"
                                if tracking_list
                                else "public_dhl"
                            )
                        )
                        title = f"DHL ({len(tracking_list)} shipments)"

                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=title,
                        data=self._user_input_data,
                    )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ACCOUNT_MODE, default=ACCOUNT_MODE_NONE
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": ACCOUNT_MODE_NONE,
                                "label": "No account login (Tracking numbers only)",
                            },
                            {
                                "value": ACCOUNT_MODE_TOKEN,
                                "label": "Session / Refresh Token (Recommended)",
                            },
                            {
                                "value": ACCOUNT_MODE_WEB,
                                "label": "Web Auth / Authorization Code",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_REFRESH_TOKEN, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_AUTH_CODE, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Optional(CONF_TRACKING_NUMBERS, default=[]): selector.TextSelector(
                    selector.TextSelectorConfig(multiple=True)
                ),
                vol.Optional(CONF_API_KEY, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_RECIPIENT_POSTAL_CODE, default=""): str,
                vol.Optional(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_account_token(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle account configuration via Refresh / Session Token (Option 1)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input.get(CONF_REFRESH_TOKEN, "").strip()
            if not token:
                errors[CONF_REFRESH_TOKEN] = "empty_token"
            else:
                session = async_get_clientsession(self.hass)
                client = DHLAPIClient(session=session)
                try:
                    await client.validate_token(token)
                except DHLAuthError:
                    errors[CONF_REFRESH_TOKEN] = "empty_token"
                except Exception as err:
                    _LOGGER.warning("DHL token validation error: %s", err)
                    errors["base"] = "cannot_connect"

                if not errors:
                    claims = decode_jwt_payload(token)
                    post_number = claims.get("post_number")
                    self._user_input_data[CONF_REFRESH_TOKEN] = token
                    self._user_input_data["account_claims"] = claims
                    if post_number:
                        self._user_input_data["post_number"] = post_number
                    tracking_list = self._user_input_data.get(CONF_TRACKING_NUMBERS, [])
                    unique_id = (
                        f"account_{post_number}"
                        if post_number
                        else f"account_{token[:10]}"
                    )
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    title = (
                        f"DHL Account {post_number} ({len(tracking_list)} shipments)"
                        if post_number
                        else f"DHL Account ({len(tracking_list)} shipments)"
                    )
                    return self.async_create_entry(
                        title=title,
                        data=self._user_input_data,
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_REFRESH_TOKEN): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                )
            }
        )
        return self.async_show_form(
            step_id="account_token",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_account_web(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle account configuration via Browser Web Auth code (Option 2)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            code = user_input.get(CONF_AUTH_CODE, "").strip()
            if not code:
                errors[CONF_AUTH_CODE] = "empty_code"
            else:
                self._user_input_data[CONF_AUTH_CODE] = code
                tracking_list = self._user_input_data.get(CONF_TRACKING_NUMBERS, [])
                unique_id = f"web_{code[:10]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"DHL Account Web ({len(tracking_list)} shipments)",
                    data=self._user_input_data,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_AUTH_CODE): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                )
            }
        )
        return self.async_show_form(
            step_id="account_web",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle initiation of re-authentication flow."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm re-authentication and update token."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            token = user_input.get(CONF_REFRESH_TOKEN, "").strip()
            if not token:
                errors[CONF_REFRESH_TOKEN] = "empty_token"
            else:
                session = async_get_clientsession(self.hass)
                client = DHLAPIClient(session=session)
                try:
                    await client.validate_token(token)
                except DHLAuthError:
                    errors[CONF_REFRESH_TOKEN] = "empty_token"
                except Exception as err:
                    _LOGGER.warning("DHL token reauth validation error: %s", err)
                    errors["base"] = "cannot_connect"

                if not errors:
                    claims = decode_jwt_payload(token)
                    post_number = claims.get("post_number") or reauth_entry.data.get(
                        "post_number"
                    )
                    merged_claims = {
                        **reauth_entry.data.get("account_claims", {}),
                        **claims,
                    }
                    return self.async_update_reload_and_abort(
                        reauth_entry,
                        data={
                            **reauth_entry.data,
                            CONF_REFRESH_TOKEN: token,
                            "account_claims": merged_claims,
                            "post_number": post_number,
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_REFRESH_TOKEN): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                )
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )


class DHLOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle DHL options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self._config_entry = config_entry

    @property
    def config_entry(self) -> config_entries.ConfigEntry:
        """Return the config entry."""
        return getattr(self, "_config_entry", None) or super().config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        current_data = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            tracking_list = _clean_tracking_list(
                user_input.get(CONF_TRACKING_NUMBERS, "")
            )
            account_mode = user_input.get(
                CONF_ACCOUNT_MODE,
                current_data.get(CONF_ACCOUNT_MODE, ACCOUNT_MODE_NONE),
            )
            refresh_token = user_input.get(
                CONF_REFRESH_TOKEN, current_data.get(CONF_REFRESH_TOKEN, "")
            )
            auth_code = user_input.get(
                CONF_AUTH_CODE, current_data.get(CONF_AUTH_CODE, "")
            )

            if not tracking_list and account_mode == ACCOUNT_MODE_NONE:
                errors[CONF_TRACKING_NUMBERS] = "empty_tracking_numbers"
            elif account_mode == ACCOUNT_MODE_TOKEN and not refresh_token:
                errors[CONF_REFRESH_TOKEN] = "empty_token"
            elif account_mode == ACCOUNT_MODE_WEB and not auth_code:
                errors[CONF_AUTH_CODE] = "empty_code"
            else:
                if account_mode == ACCOUNT_MODE_TOKEN and refresh_token:
                    session = async_get_clientsession(self.hass)
                    client = DHLAPIClient(session=session)
                    try:
                        await client.validate_token(refresh_token)
                    except DHLAuthError:
                        errors[CONF_REFRESH_TOKEN] = "empty_token"
                    except Exception as err:
                        _LOGGER.warning(
                            "DHL token validation error in options: %s", err
                        )
                        errors["base"] = "cannot_connect"

                if not errors:
                    postal_code = (
                        user_input.get(CONF_RECIPIENT_POSTAL_CODE, "").strip() or None
                    )
                    api_key = user_input.get(CONF_API_KEY, "").strip()
                    claims = decode_jwt_payload(refresh_token) if refresh_token else {}
                    post_number = claims.get("post_number") or current_data.get(
                        "post_number"
                    )
                    merged_claims = {
                        **current_data.get("account_claims", {}),
                        **claims,
                    }

                    return self.async_create_entry(
                        title="",
                        data={
                            CONF_API_KEY: api_key,
                            CONF_TRACKING_NUMBERS: tracking_list,
                            CONF_RECIPIENT_POSTAL_CODE: postal_code,
                            CONF_ACCOUNT_MODE: account_mode,
                            CONF_REFRESH_TOKEN: refresh_token,
                            CONF_AUTH_CODE: auth_code,
                            CONF_UPDATE_INTERVAL: user_input.get(
                                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                            ),
                            "account_claims": merged_claims,
                            "post_number": post_number,
                        },
                    )

        current_numbers = current_data.get(CONF_TRACKING_NUMBERS, [])
        if not isinstance(current_numbers, list):
            current_numbers = [str(current_numbers)] if current_numbers else []

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ACCOUNT_MODE,
                    default=current_data.get(CONF_ACCOUNT_MODE, ACCOUNT_MODE_NONE),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": ACCOUNT_MODE_NONE,
                                "label": "No account login (Tracking numbers only)",
                            },
                            {
                                "value": ACCOUNT_MODE_TOKEN,
                                "label": "Session / Refresh Token (Recommended)",
                            },
                            {
                                "value": ACCOUNT_MODE_WEB,
                                "label": "Web Auth / Authorization Code",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_TRACKING_NUMBERS,
                    default=current_numbers,
                ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_REFRESH_TOKEN,
                    default=current_data.get(CONF_REFRESH_TOKEN, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(
                    CONF_AUTH_CODE,
                    default=current_data.get(CONF_AUTH_CODE, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Optional(
                    CONF_API_KEY,
                    default=current_data.get(CONF_API_KEY) or "",
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(
                    CONF_RECIPIENT_POSTAL_CODE,
                    default=current_data.get(CONF_RECIPIENT_POSTAL_CODE) or "",
                ): str,
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=current_data.get(
                        CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
