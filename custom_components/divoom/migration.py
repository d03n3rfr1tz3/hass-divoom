"""Find, convert and rewrite legacy notify.divoom_* calls.

The conversion engine below is pure. The scan over the loaded automations and
scripts, the file rewrite and the repair issue build on top of it.
"""
import copy
import logging
import os
import re
import shutil
from dataclasses import dataclass, field

import voluptuous as vol

from homeassistant.components import automation, script
from homeassistant.components.notify import ATTR_DATA, ATTR_MESSAGE
from homeassistant.config import AUTOMATION_CONFIG_PATH, SCRIPT_CONFIG_PATH
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import slugify
from homeassistant.util.dt import utcnow
from homeassistant.util.file import write_utf8_file_atomic
from homeassistant.util.yaml import dump, load_yaml, load_yaml_dict, parse_yaml

from .const import CONF_DEVICE, DOMAIN
from .notify import (
    PARAM_BRIGHTNESS,
    PARAM_COLOR,
    PARAM_BACKGROUND_COLOR,
    PARAM_FOREGROUND_COLOR,
    PARAM_MODE,
    PARAM_NUMBER,
    PARAM_TEMP,
    PARAM_TEXT,
    PARAM_VALUE,
    PARAM_VOLUME,
    VALID_MODES,
)
from .services import (
    GAMECONTROL_VALUES,
    KEYBOARD_VALUES,
    SERVICE_SCHEMAS,
    TEMPERATURE_UNITS,
    device_slug,
)

_LOGGER = logging.getLogger(__package__)

NESTED_KEYS = (
    "action",
    "actions",
    "sequence",
    "default",
    "then",
    "else",
    "parallel",
    "choose",
    "repeat",
)
ACTION_KEYS = ("action", "service")
DATA_KEYS = ("data", "data_template")

TEMPLATE_MARKERS = ("{{", "{%")

REASON_TEMPLATED_MODE = "templated_mode"
REASON_UNKNOWN_MODE = "unknown_mode"
REASON_UNKNOWN_FIELD = "unknown_field"
REASON_MISSING_FIELD = "missing_field"
REASON_SCHEMA = "schema"


@dataclass
class Conversion:
    """The outcome of looking at a single legacy step."""

    mode: str | None
    data: dict | None
    reason: str | None

    @property
    def ok(self) -> bool:
        return self.reason is None


def has_template(value) -> bool:
    """Whether a value contains a Jinja template anywhere inside it."""
    if isinstance(value, str):
        return any(marker in value for marker in TEMPLATE_MARKERS)
    if isinstance(value, dict):
        return any(has_template(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(has_template(item) for item in value)
    return False


def iter_steps(node):
    """Yield every dict below node that could be an action step."""
    if isinstance(node, list):
        for item in node:
            yield from iter_steps(item)
        return

    if not isinstance(node, dict):
        return

    yield node
    for key in NESTED_KEYS:
        yield from iter_steps(node.get(key))


def legacy_service(step, services) -> str | None:
    """The notify service this step calls, if it is one of ours."""
    if not isinstance(step, dict):
        return None

    for key in ACTION_KEYS:
        name = step.get(key)
        if isinstance(name, str) and name in services:
            return name

    return None


def _payload(step):
    """The notify payload and the nested data dict holding the mode params."""
    for key in DATA_KEYS:
        outer = step.get(key)
        if isinstance(outer, dict):
            inner = outer.get(ATTR_DATA)
            return outer, inner if isinstance(inner, dict) else {}
    return {}, {}


def _first_not_none(data, *keys):
    for key in keys:
        if data.get(key) is not None:
            return data[key]
    return None


def _first_truthy(data, *keys):
    """The legacy `a or b or c` chains, where a falsy value falls through."""
    for key in keys:
        if data.get(key):
            return data[key]
    return None


def _collapse(params, sources, target, value):
    """Drop every source key and put value under target, keeping key order."""
    collapsed = {}
    placed = False
    for key, current in params.items():
        if key not in sources:
            collapsed[key] = current
            continue
        if not placed:
            collapsed[target] = value
            placed = True
    if not placed and value is not None:
        collapsed[target] = value
    if collapsed.get(target) is None:
        collapsed.pop(target, None)
    return collapsed


def _as_unit(value):
    """The legacy 0/1 and bare C/F spellings for a temperature unit."""
    if value in (0, 1):
        return TEMPERATURE_UNITS[value]
    if isinstance(value, str):
        stripped = value.strip().upper().lstrip("°")
        if stripped in ("C", "F"):
            return "°{}".format(stripped)
    return value


def _from_index(value, names):
    """The legacy protocol number for a value the service now spells out."""
    if isinstance(value, bool) or not isinstance(value, int):
        return value
    return names[value] if 0 <= value < len(names) else value


def _split_colors(params):
    """color: [[foreground], [background]] into the two separate params."""
    color = params.get(PARAM_COLOR)
    if not isinstance(color, list) or not color or not isinstance(color[0], list):
        return params

    split = {}
    for key, value in params.items():
        if key != PARAM_COLOR:
            split[key] = value
            continue
        split[PARAM_FOREGROUND_COLOR] = color[0]
        if len(color) > 1:
            split[PARAM_BACKGROUND_COLOR] = color[1]

    for key in (PARAM_FOREGROUND_COLOR, PARAM_BACKGROUND_COLOR):
        if params.get(key) is not None:
            split[key] = params[key]

    return split


def convert_params(mode, payload) -> dict:
    """The legacy data dict as the divoom.<mode> service wants it."""
    params = {key: value for key, value in payload.items() if key != PARAM_MODE}

    if mode == "brightness":
        value = _first_not_none(payload, PARAM_BRIGHTNESS, PARAM_NUMBER, PARAM_VALUE)
        params = _collapse(params, (PARAM_BRIGHTNESS, PARAM_NUMBER, PARAM_VALUE), PARAM_BRIGHTNESS, value)

    elif mode == "volume":
        value = _first_truthy(payload, PARAM_VOLUME, PARAM_NUMBER, PARAM_VALUE)
        params = _collapse(params, (PARAM_VOLUME, PARAM_NUMBER, PARAM_VALUE), PARAM_VOLUME, value)

    elif mode == "text":
        value = _first_truthy(payload, PARAM_TEXT, PARAM_VALUE)
        params = _collapse(params, (PARAM_TEXT, PARAM_VALUE), PARAM_TEXT, value)

    elif mode == "temperature":
        value = _first_not_none(payload, PARAM_TEMP, PARAM_VALUE)
        params = _collapse(params, (PARAM_TEMP, PARAM_VALUE), PARAM_VALUE, _as_unit(value))

    elif mode == "keyboard":
        params[PARAM_VALUE] = _from_index(_shift(params.get(PARAM_VALUE)), KEYBOARD_VALUES)

    elif mode == "gamecontrol":
        params[PARAM_VALUE] = _from_index(params.get(PARAM_VALUE), GAMECONTROL_VALUES)

    if PARAM_FOREGROUND_COLOR in SERVICE_SCHEMAS[mode].schema:
        params = _split_colors(params)

    return params


def _shift(value):
    """The keyboard effect runs from -1, the service list from 0."""
    if isinstance(value, bool) or not isinstance(value, int):
        return value
    return value + 1


def _check(mode, params) -> str | None:
    """Validate against the schema the real service uses, ignoring templates."""
    schema = SERVICE_SCHEMAS[mode].schema
    validators = {str(marker): validator for marker, validator in schema.items()}
    required = {str(marker) for marker in schema if isinstance(marker, vol.Required)}

    if set(params) - set(validators):
        return REASON_UNKNOWN_FIELD

    if required - set(params):
        return REASON_MISSING_FIELD

    for key, value in params.items():
        if has_template(value):
            continue
        try:
            validators[key](value)
        except (vol.Invalid, ValueError, TypeError):
            return REASON_SCHEMA

    return None


def convert_step(step, services) -> Conversion | None:
    """None if this step is not a legacy divoom notify call."""
    service = legacy_service(step, services)
    if service is None:
        return None

    outer, inner = _payload(step)
    mode = inner.get(PARAM_MODE) or outer.get(ATTR_MESSAGE)

    if has_template(mode):
        return Conversion(None, None, REASON_TEMPLATED_MODE)

    if mode not in VALID_MODES:
        return Conversion(mode if isinstance(mode, str) else None, None, REASON_UNKNOWN_MODE)

    params = convert_params(mode, inner)
    params = {CONF_DEVICE: services[service], **params}

    reason = _check(mode, params)
    return Conversion(mode, params if reason is None else None, reason)


def apply_conversion(step, conversion) -> None:
    """Rewrite the step in place, keeping the position of every other key."""
    rewritten = {}
    for key, value in step.items():
        if key in ACTION_KEYS:
            rewritten["action"] = "{}.{}".format(DOMAIN, conversion.mode)
        elif key in DATA_KEYS:
            rewritten["data"] = conversion.data
        else:
            rewritten[key] = value

    step.clear()
    step.update(rewritten)


def preview_config(config, services):
    """(before, after) for every convertible step, leaving config untouched."""
    pairs = []

    for step in iter_steps(copy.deepcopy(config)):
        conversion = convert_step(step, services)
        if conversion is None or not conversion.ok:
            continue
        before = dict(step)
        apply_conversion(step, conversion)
        pairs.append((before, dict(step)))

    return pairs


def convert_config(config, services):
    """Convert every legacy step in a raw automation or script config.

    Mutates config in place and returns (converted, failures).
    """
    converted = 0
    failures = []

    for step in list(iter_steps(config)):
        conversion = convert_step(step, services)
        if conversion is None:
            continue
        if not conversion.ok:
            failures.append(conversion)
            continue
        apply_conversion(step, conversion)
        converted += 1

    return converted, failures


ISSUE_LEGACY_NOTIFY = "legacy_notify_usage"

AUTOMATION = "automation"
SCRIPT = "script"

UNSAFE_TAGS = ("!secret", "!include", "!env_var")
MERGE_KEY = re.compile(r"^\s*<<\s*:", re.MULTILINE)
ANCHOR = re.compile(r"^\s*(?:-\s*|[\w.-]+\s*:\s*)[&*][\w-]+\s*$", re.MULTILINE)


@dataclass
class Finding:
    """One automation or script that still calls the legacy notify service."""

    kind: str
    entity_id: str
    name: str
    key: str | None
    calls: int
    reasons: list[str] = field(default_factory=list)

    @property
    def writable(self) -> bool:
        """Whether the rewrite can address it at all."""
        return self.key is not None and not self.reasons

    @property
    def link(self) -> str | None:
        if self.key is None:
            return None
        return "/config/{0}/edit/{1}".format(self.kind, self.key)


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(finding.calls for finding in self.findings)

    @property
    def writable(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.writable]

    @property
    def manual(self) -> list[Finding]:
        return [finding for finding in self.findings if not finding.writable]

    def markdown(self) -> str:
        lines = []
        for finding in self.findings:
            label = "`{0}`".format(finding.entity_id)
            if finding.link:
                label = "[{0}]({1})".format(finding.name, finding.link)
            note = "" if finding.writable else " — manuell"
            lines.append("- {0}{1}".format(label, note))
        return "\n".join(lines)


@callback
def service_map(hass: HomeAssistant) -> dict[str, str]:
    """Every notify service this integration owns, mapped to its device slug."""
    services = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        name = entry.data.get(CONF_NAME)
        if name:
            services["notify.{0}".format(slugify(name))] = device_slug(entry)
    return services


def _entities(hass: HomeAssistant):
    """(kind, entity) for every automation and script currently loaded."""
    component = hass.data.get(automation.DATA_COMPONENT)
    if component is not None:
        for entity in component.entities:
            yield AUTOMATION, entity

    component = hass.data.get(script.DOMAIN)
    if component is not None:
        for entity in component.entities:
            yield SCRIPT, entity


@callback
def async_scan(hass: HomeAssistant) -> ScanResult:
    """Look for legacy calls without touching anything."""
    result = ScanResult()
    services = service_map(hass)
    if not services:
        return result

    for kind, entity in _entities(hass):
        raw_config = entity.raw_config
        if not raw_config:
            continue

        converted, failures = convert_config(copy.deepcopy(raw_config), services)
        if not converted and not failures:
            continue

        key = entity.unique_id
        if entity.referenced_blueprint is not None:
            key = None

        result.findings.append(
            Finding(
                kind=kind,
                entity_id=entity.entity_id,
                name=entity.name or entity.entity_id,
                key=key,
                calls=converted + len(failures),
                reasons=sorted({failure.reason for failure in failures}),
            )
        )

    return result


@callback
def async_preview(hass: HomeAssistant, limit: int = 8) -> str:
    """A before/after listing of what the rewrite would do."""
    services = service_map(hass)
    blocks = []

    for _, entity in _entities(hass):
        if not entity.raw_config:
            continue
        for before, after in preview_config(entity.raw_config, services):
            blocks.append(
                "**{0}**\n```yaml\n{1}```\n```yaml\n{2}```".format(
                    entity.name or entity.entity_id, dump([before]), dump([after])
                )
            )

    shown = blocks[:limit]
    if len(blocks) > limit:
        shown.append("… (+{0})".format(len(blocks) - limit))

    return "\n\n".join(shown)


def unsafe_reason(text: str) -> str | None:
    """Why this file cannot be rewritten without losing information."""
    for tag in UNSAFE_TAGS:
        if tag in text:
            return tag.lstrip("!")
    if MERGE_KEY.search(text):
        return "merge_key"
    if ANCHOR.search(text):
        return "anchor"
    return None


def _preflight(paths) -> dict[str, str]:
    """Blocking. The files that must not be rewritten, with the reason."""
    blocked = {}
    for kind, path in paths.items():
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as handle:
            reason = unsafe_reason(handle.read())
        if reason:
            blocked[kind] = reason
    return blocked


def _backup(path: str) -> str:
    """A raw byte copy, so the comments the rewrite drops survive somewhere."""
    target = "{0}.divoom-backup-{1:%Y%m%d%H%M%S}".format(path, utcnow())
    shutil.copy2(path, target)
    return target


def _render(path: str, data) -> str:
    contents = dump(data)

    if parse_yaml(contents) != data:
        raise HomeAssistantError("YAML round trip check failed for {0}".format(path))

    return contents


def _migrate_files(paths, services):
    """Blocking. Rewrites the files and returns (changed kinds, converted count)."""
    changed = []
    pending = []
    converted = 0

    for kind, path in paths.items():
        if not os.path.isfile(path):
            continue

        if kind == AUTOMATION:
            data = load_yaml(path)
            configs = data if isinstance(data, list) else []
        else:
            data = load_yaml_dict(path)
            configs = list(data.values())

        count = 0
        for config in configs:
            found, _ = convert_config(config, services)
            count += found

        if not count:
            continue

        pending.append((path, _render(path, data)))
        changed.append(kind)
        converted += count

    for path, contents in pending:
        _backup(path)
        write_utf8_file_atomic(path, contents.encode("utf-8"), mode="wb")

    return changed, converted


async def async_migrate(hass: HomeAssistant):
    """Rewrite the config files. Returns (changed kinds, converted, blocked)."""
    paths = {
        AUTOMATION: hass.config.path(AUTOMATION_CONFIG_PATH),
        SCRIPT: hass.config.path(SCRIPT_CONFIG_PATH),
    }

    blocked = await hass.async_add_executor_job(_preflight, paths)
    if blocked:
        return [], 0, blocked

    services = service_map(hass)
    changed, converted = await hass.async_add_executor_job(_migrate_files, paths, services)

    for kind in changed:
        if hass.services.has_service(kind, "reload"):
            await hass.services.async_call(kind, "reload", {}, blocking=True)

    return changed, converted, {}


@callback
def async_update_issue(hass: HomeAssistant, result: ScanResult) -> None:
    """Raise, refresh or clear the repair issue for the current scan."""
    if not result.findings:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_LEGACY_NOTIFY)
        return

    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_LEGACY_NOTIFY,
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_LEGACY_NOTIFY,
        translation_placeholders={
            "count": str(result.total),
            "items": result.markdown(),
        },
    )


@callback
def async_rescan(hass: HomeAssistant) -> ScanResult:
    """Scan and bring the issue in line with the result."""
    result = async_scan(hass)
    async_update_issue(hass, result)
    _LOGGER.debug("Divoom: found {} legacy notify calls".format(result.total))
    return result
