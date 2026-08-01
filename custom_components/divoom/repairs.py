"""Repair flow that migrates legacy notify.divoom_* calls."""
import logging

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .migration import (
    ISSUE_LEGACY_NOTIFY,
    async_migrate,
    async_preview,
    async_reason_labels,
    async_rescan,
    async_scan,
)

_LOGGER = logging.getLogger(__package__)

CONF_CONFIRM = "confirm"


class LegacyNotifyRepairFlow(RepairsFlow):
    """Offer the automatic rewrite, a preview of it, or ignoring the issue."""

    async def async_step_init(self, user_input=None):
        result = async_scan(self.hass)
        if not result.findings:
            return self.async_abort(reason="nothing_to_do")

        labels = await async_reason_labels(self.hass)
        return self.async_show_menu(
            step_id="init",
            menu_options=["apply", "preview", "ignore"],
            description_placeholders={
                "count": str(result.total),
                "items": result.markdown(labels),
            },
        )

    async def async_step_apply(self, user_input=None):
        result = async_scan(self.hass)

        if user_input is None:
            labels = await async_reason_labels(self.hass)
            return self.async_show_form(
                step_id="apply",
                data_schema=vol.Schema({vol.Required(CONF_CONFIRM, default=False): bool}),
                description_placeholders={
                    "writable": str(len(result.writable)),
                    "manual": str(len(result.manual)),
                    "items": result.markdown(labels),
                },
            )

        if not user_input.get(CONF_CONFIRM):
            return await self.async_step_init()

        try:
            changed, converted, blocked = await async_migrate(self.hass)
        except Exception as err:
            _LOGGER.error("Divoom: migration failed. %s", err, exc_info=True)
            return self.async_abort(
                reason="migration_failed", description_placeholders={"error": str(err)}
            )

        if blocked:
            return self.async_abort(
                reason="unsafe_file",
                description_placeholders={
                    "files": ", ".join(sorted(blocked)),
                    "reason": ", ".join(sorted(set(blocked.values()))),
                },
            )

        remaining = await async_rescan(self.hass)
        if remaining.findings:
            labels = await async_reason_labels(self.hass)
            return self.async_abort(
                reason="manual_migration_required",
                description_placeholders={
                    "converted": str(converted),
                    "items": remaining.markdown(labels),
                },
            )

        return self.async_create_entry(title="", data={})

    async def async_step_preview(self, user_input=None):
        if user_input is None:
            return self.async_show_form(
                step_id="preview",
                data_schema=vol.Schema({}),
                description_placeholders={"preview": async_preview(self.hass)},
                last_step=False,
            )

        return await self.async_step_init()

    async def async_step_ignore(self, user_input=None):
        ir.async_get(self.hass).async_ignore(DOMAIN, self.issue_id, True)
        return self.async_abort(reason="issue_ignored")


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data):
    """Create the flow handling this issue."""
    if issue_id == ISSUE_LEGACY_NOTIFY:
        return LegacyNotifyRepairFlow()

    raise ValueError("Unknown issue {0}".format(issue_id))
