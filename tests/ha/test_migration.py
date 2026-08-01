"""Tests for the repair that migrates notify.divoom_* to the divoom.* actions.

The conversion engine is pure, so most of this runs without hass. What needs
hass is the scan over raw_config and the file rewrite, which gets a tmp_path
config dir via the config_dir fixture.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import voluptuous as vol

from homeassistant import loader
from homeassistant.components import automation
from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir, translation
from homeassistant.helpers.translation import recursive_flatten
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml, parse_yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.divoom import migration as migration_module
from custom_components.divoom.const import CONF_ENTRY_ID, DOMAIN
from custom_components.divoom.devices.aurabox import Aurabox
from custom_components.divoom.devices.ditoo import Ditoo
from custom_components.divoom.devices.pixoo import Pixoo
from custom_components.divoom.devices.timeboxmini import TimeboxMini
from custom_components.divoom.migration import (
    ISSUE_LEGACY_NOTIFY,
    REASON_MISSING_FIELD,
    REASON_TEMPLATED_MODE,
    REASON_UNKNOWN_FIELD,
    REASON_UNKNOWN_MODE,
    async_migrate,
    async_rescan,
    async_scan,
    convert_config,
    convert_step,
    iter_steps,
    service_map,
    unsafe_reason,
)
from custom_components.divoom.repairs import LegacyNotifyRepairFlow

from .test_notify import make_mocked_service

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

COMPONENT_PATH = Path(__file__).parents[2] / "custom_components" / "divoom"

SERVICES = {"notify.divoom_test": "ENTRY1"}


def step(message, data=None, key="action", service="notify.divoom_test"):
    """A legacy notify call as it appears in a raw automation config."""
    payload = {"message": message}
    if data is not None:
        payload["data"] = data
    return {key: service, "data": payload}


# (name, legacy step, expected new data)
CONVERSION_CASES = [
    ("modern notation", step("clock", {"clock": 0, "twentyfour": True}),
     {CONF_ENTRY_ID: "ENTRY1", "clock": 0, "twentyfour": True}),
    ("mode inside data", step("", {"mode": "brightness", "number": 75}),
     {CONF_ENTRY_ID: "ENTRY1", "brightness": 75}),
    ("mode in data wins", step("clock", {"mode": "on"}),
     {CONF_ENTRY_ID: "ENTRY1"}),
    ("service key", step("brightness", {"brightness": 30}, key="service"),
     {CONF_ENTRY_ID: "ENTRY1", "brightness": 30}),
    ("brightness zero survives", step("brightness", {"value": 0}),
     {CONF_ENTRY_ID: "ENTRY1", "brightness": 0}),
    ("brightness via number", step("brightness", {"number": 42}),
     {CONF_ENTRY_ID: "ENTRY1", "brightness": 42}),
    ("volume via value", step("volume", {"value": 60}),
     {CONF_ENTRY_ID: "ENTRY1", "volume": 60}),
    ("text via value", step("text", {"value": "Hallo"}),
     {CONF_ENTRY_ID: "ENTRY1", "text": "Hallo"}),
    ("packed colors split", step("text", {"text": "Hi", "color": [[255, 0, 0], [0, 0, 255]]}),
     {CONF_ENTRY_ID: "ENTRY1", "text": "Hi", "foreground_color": [255, 0, 0], "background_color": [0, 0, 255]}),
    ("separate colors win", step("text", {"text": "Hi", "color": [[1, 1, 1], [2, 2, 2]], "foreground_color": [9, 9, 9]}),
     {CONF_ENTRY_ID: "ENTRY1", "text": "Hi", "foreground_color": [9, 9, 9], "background_color": [2, 2, 2]}),
    ("clock keeps single color", step("clock", {"clock": 1, "color": [10, 20, 30]}),
     {CONF_ENTRY_ID: "ENTRY1", "clock": 1, "color": [10, 20, 30]}),
    ("visualization colors split", step("visualization", {"number": 2, "color": [[1, 2, 3], [4, 5, 6]]}),
     {CONF_ENTRY_ID: "ENTRY1", "number": 2, "foreground_color": [1, 2, 3], "background_color": [4, 5, 6]}),
    ("keyboard previous", step("keyboard", {"value": -1}),
     {CONF_ENTRY_ID: "ENTRY1", "value": "previous"}),
    ("keyboard toggle", step("keyboard", {"value": 0}),
     {CONF_ENTRY_ID: "ENTRY1", "value": "toggle"}),
    ("keyboard next", step("keyboard", {"value": 1}),
     {CONF_ENTRY_ID: "ENTRY1", "value": "next"}),
    ("keyboard word passes through", step("keyboard", {"value": "next"}),
     {CONF_ENTRY_ID: "ENTRY1", "value": "next"}),
    ("gamecontrol go", step("gamecontrol", {"value": 0}),
     {CONF_ENTRY_ID: "ENTRY1", "value": "go"}),
    ("gamecontrol ok", step("gamecontrol", {"value": 5}),
     {CONF_ENTRY_ID: "ENTRY1", "value": "ok"}),
    ("gamecontrol down", step("gamecontrol", {"value": 4}),
     {CONF_ENTRY_ID: "ENTRY1", "value": "down"}),
    ("temperature celsius", step("temperature", {"value": 0}),
     {CONF_ENTRY_ID: "ENTRY1", "value": "°C"}),
    ("temperature fahrenheit", step("temperature", {"value": 1}),
     {CONF_ENTRY_ID: "ENTRY1", "value": "°F"}),
    ("temperature via temp", step("temperature", {"temp": "°F"}),
     {CONF_ENTRY_ID: "ENTRY1", "value": "°F"}),
    ("weather stays combined", step("weather", {"value": "25°C", "weather": "rainy"}),
     {CONF_ENTRY_ID: "ENTRY1", "value": "25°C", "weather": "rainy"}),
    ("weather numeric condition", step("weather", {"value": 12, "weather": 6}),
     {CONF_ENTRY_ID: "ENTRY1", "value": 12, "weather": 6}),
    ("no data at all", step("on"),
     {CONF_ENTRY_ID: "ENTRY1"}),
    ("template value kept", step("text", {"text": "{{ states('sensor.t') }}"}),
     {CONF_ENTRY_ID: "ENTRY1", "text": "{{ states('sensor.t') }}"}),
]


@pytest.mark.parametrize("name,legacy,expected", CONVERSION_CASES, ids=[c[0] for c in CONVERSION_CASES])
def test_conversion_produces_the_expected_service_data(name, legacy, expected):
    conversion = convert_step(legacy, SERVICES)

    assert conversion is not None and conversion.ok, conversion
    assert conversion.data == expected


# (name, legacy step, reason)
MANUAL_CASES = [
    ("templated mode", step("{{ states('input_select.mode') }}", {}), REASON_TEMPLATED_MODE),
    ("templated mode in data", step("", {"mode": "{{ x }}"}), REASON_TEMPLATED_MODE),
    ("unknown mode", step("teleport", {}), REASON_UNKNOWN_MODE),
    # notify.py resolves volume through an `or` chain, so 0 falls through to
    # None, which the required volume field cannot express
    ("volume zero is ambiguous", step("volume", {"volume": 0}), REASON_MISSING_FIELD),
    # the signal action takes no colors, so there is nothing to migrate them to
    ("signal with colors", step("signal", {"number": 1, "color": [[1, 2, 3]]}), REASON_UNKNOWN_FIELD),
    ("out of range", step("brightness", {"brightness": 500}), "schema"),
]


@pytest.mark.parametrize("name,legacy,reason", MANUAL_CASES, ids=[c[0] for c in MANUAL_CASES])
def test_unconvertible_steps_are_reported_not_guessed(name, legacy, reason):
    conversion = convert_step(legacy, SERVICES)

    assert conversion is not None
    assert not conversion.ok
    assert conversion.reason == reason
    assert conversion.data is None


def test_foreign_services_are_left_alone():
    assert convert_step(step("hi", key="action", service="notify.mobile_app"), SERVICES) is None
    assert convert_step({"action": "light.turn_on", "target": {"entity_id": "light.x"}}, SERVICES) is None


@pytest.mark.parametrize(
    "wrapper",
    [
        lambda inner: {"actions": [inner]},
        lambda inner: {"action": [inner]},
        lambda inner: {"sequence": [inner]},
        lambda inner: {"actions": [{"choose": [{"conditions": [], "sequence": [inner]}]}]},
        lambda inner: {"actions": [{"choose": [], "default": [inner]}]},
        lambda inner: {"actions": [{"if": [], "then": [inner]}]},
        lambda inner: {"actions": [{"if": [], "then": [], "else": [inner]}]},
        lambda inner: {"actions": [{"repeat": {"count": 2, "sequence": [inner]}}]},
        lambda inner: {"actions": [{"parallel": [{"sequence": [inner]}]}]},
        lambda inner: {"actions": [{"parallel": [inner]}]},
    ],
)
def test_walker_reaches_every_nesting_form(wrapper):
    config = wrapper(step("on", {}))

    converted, failures = convert_config(config, SERVICES)

    assert (converted, failures) == (1, [])
    assert "divoom.on" in json.dumps(config)


def test_rewrite_keeps_the_other_keys_and_their_order():
    config = {
        "actions": [
            {
                "alias": "Say hello",
                "action": "notify.divoom_test",
                "data": {"message": "text", "data": {"text": "Hi"}},
                "enabled": True,
                "continue_on_error": True,
            }
        ]
    }

    convert_config(config, SERVICES)

    assert list(config["actions"][0]) == ["alias", "action", "data", "enabled", "continue_on_error"]
    assert config["actions"][0]["action"] == "divoom.text"
    assert config["actions"][0]["enabled"] is True


def test_data_template_is_migrated_to_data():
    config = {"actions": [{"action": "notify.divoom_test", "data_template": {"message": "on"}}]}

    convert_config(config, SERVICES)

    assert config["actions"][0] == {"action": "divoom.on", "data": {CONF_ENTRY_ID: "ENTRY1"}}


# --- parity between the legacy path and the migrated call -------------------


# keyboard, gamecontrol and temperature are the modes where the migration
# rewrites the value itself; call_mode hands it to the device untouched, so
# their parity is a device level question and is asserted separately below
REMAPPED_MODES = ("keyboard", "gamecontrol", "temperature")

PARITY_CASES = [
    case
    for case in CONVERSION_CASES
    if "template" not in case[0]
    and not case[0].startswith(REMAPPED_MODES)
]


@pytest.mark.parametrize("name,legacy,expected", PARITY_CASES, ids=[c[0] for c in PARITY_CASES])
def test_migrated_call_behaves_like_the_legacy_one(name, legacy, expected):
    """The whole point of the migration: the device must see the same calls.

    One end runs the original notify payload through send_message, the other
    runs the converted params through the same dispatch the divoom.* services
    use, and both mocked devices must have been driven identically.
    """
    conversion = convert_step(dict(legacy), SERVICES)
    mode = conversion.mode
    params = {key: value for key, value in conversion.data.items() if key != CONF_ENTRY_ID}

    payload = legacy["data"]
    via_legacy = make_mocked_service()
    via_legacy.send_message(payload.get("message", ""), data=payload.get("data"))

    via_service = make_mocked_service()
    via_service.call_mode(mode, params)

    assert via_service._device.mock_calls == via_legacy._device.mock_calls


# (device class, method, legacy step)
REMAP_CASES = [
    (Ditoo, "send_keyboard", step("keyboard", {"value": -1})),
    (Ditoo, "send_keyboard", step("keyboard", {"value": 0})),
    (Ditoo, "send_keyboard", step("keyboard", {"value": 1})),
    (Pixoo, "send_gamecontrol", step("gamecontrol", {"value": 0})),
    (Pixoo, "send_gamecontrol", step("gamecontrol", {"value": 1})),
    (Pixoo, "send_gamecontrol", step("gamecontrol", {"value": 2})),
    (Pixoo, "send_gamecontrol", step("gamecontrol", {"value": 3})),
    (Pixoo, "send_gamecontrol", step("gamecontrol", {"value": 4})),
    (Pixoo, "send_gamecontrol", step("gamecontrol", {"value": 5})),
    (Aurabox, "show_temperature", step("temperature", {"value": 0})),
    (Aurabox, "show_temperature", step("temperature", {"value": 1})),
    (TimeboxMini, "show_temperature", step("temperature", {"value": 0})),
    (TimeboxMini, "show_temperature", step("temperature", {"value": 1})),
]

REMAP_IDS = [
    "{0}-{1}".format(case[1], case[2]["data"]["data"]["value"]) for case in REMAP_CASES
]


@pytest.mark.parametrize("device_cls,method,legacy", REMAP_CASES, ids=REMAP_IDS)
def test_remapped_values_reach_the_device_identically(device_cls, method, legacy):
    """The migration spells out the numbers these three modes used to take,
    so the device has to end up sending the very same bytes for both."""
    value = legacy["data"]["data"]["value"]
    migrated = convert_step(dict(legacy), SERVICES).data["value"]

    by_number = device_cls(mac="11:22:33:44:55:66")
    by_number.send_command = Mock()
    by_name = device_cls(mac="11:22:33:44:55:66")
    by_name.send_command = Mock()

    getattr(by_number, method)(value=value)
    getattr(by_name, method)(value=migrated)

    assert by_name.send_command.call_args_list == by_number.send_command.call_args_list


# --- the file rewrite -------------------------------------------------------


AUTOMATIONS_YAML = """\
# Guten Morgen, Küche
- id: '1699999999999'
  alias: Küche Guten Morgen
  triggers:
  - trigger: time
    at: 07:00:00
  actions:
  - action: notify.divoom_test
    data:
      message: ''
      data:
        mode: text
        text: '{{ states(''sensor.aussentemperatur'') }} °C'
  - action: notify.divoom_test
    data:
      message: brightness
      data:
        number: 75
- id: '1699999999998'
  alias: Unrelated
  actions:
  - action: light.turn_on
    target:
      entity_id: light.kueche
"""

SCRIPTS_YAML = """\
gute_nacht:
  alias: Gute Nacht
  sequence:
  - action: notify.divoom_test
    data:
      message: 'off'
      data: {}
"""


def register_entry(hass, name="Divoom Test", mac="11:22:33:44:55:66"):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_MAC: mac, CONF_NAME: name}, title=name
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def yaml_files(config_dir):
    automations = config_dir / "automations.yaml"
    scripts = config_dir / "scripts.yaml"
    automations.write_text(AUTOMATIONS_YAML, encoding="utf-8")
    scripts.write_text(SCRIPTS_YAML, encoding="utf-8")
    return automations, scripts


async def test_service_map_derives_the_notify_name_from_the_entry(hass):
    entry = register_entry(hass, name="Divoom Test")

    assert service_map(hass) == {"notify.divoom_test": entry.entry_id}


async def test_migrate_rewrites_both_files(hass, yaml_files):
    automations, scripts = yaml_files
    entry = register_entry(hass)
    async_mock_service(hass, "automation", "reload", schema=vol.Schema({}))
    async_mock_service(hass, "script", "reload", schema=vol.Schema({}))

    changed, converted, blocked = await async_migrate(hass)

    assert sorted(changed) == ["automation", "script"]
    assert converted == 3
    assert blocked == {}

    migrated = load_yaml(str(automations))
    assert migrated[0]["actions"][0]["action"] == "divoom.text"
    assert migrated[0]["actions"][0]["data"] == {
        CONF_ENTRY_ID: entry.entry_id,
        "text": "{{ states('sensor.aussentemperatur') }} °C",
    }
    assert migrated[0]["actions"][1]["data"] == {
        CONF_ENTRY_ID: entry.entry_id,
        "brightness": 75,
    }
    # the untouched automation keeps working
    assert migrated[1]["actions"][0]["action"] == "light.turn_on"

    assert load_yaml(str(scripts))["gute_nacht"]["sequence"][0]["action"] == "divoom.off"


async def test_migrate_writes_real_utf8(hass, yaml_files):
    """write_utf8_file_atomic hands text straight to AtomicWriter without an
    encoding, so anything but bytes would be written in the platform locale
    and °C plus umlauts would come back undecodable."""
    automations, _ = yaml_files
    register_entry(hass)
    async_mock_service(hass, "automation", "reload", schema=vol.Schema({}))
    async_mock_service(hass, "script", "reload", schema=vol.Schema({}))

    await async_migrate(hass)

    raw = automations.read_bytes().decode("utf-8")
    assert "°C" in raw
    assert "Küche" in raw


async def test_migrate_reloads_only_what_it_changed(hass, config_dir):
    (config_dir / "automations.yaml").write_text(AUTOMATIONS_YAML, encoding="utf-8")
    register_entry(hass)
    automation_reload = async_mock_service(hass, "automation", "reload", schema=vol.Schema({}))
    script_reload = async_mock_service(hass, "script", "reload", schema=vol.Schema({}))

    await async_migrate(hass)

    assert len(automation_reload) == 1
    # script.reload rejects any payload, so it must be called empty
    assert dict(automation_reload[0].data) == {}
    assert script_reload == []


async def test_migrate_backs_up_the_original_bytes(hass, yaml_files):
    automations, _ = yaml_files
    original = automations.read_bytes()
    register_entry(hass)
    async_mock_service(hass, "automation", "reload", schema=vol.Schema({}))
    async_mock_service(hass, "script", "reload", schema=vol.Schema({}))

    await async_migrate(hass)

    backups = list(automations.parent.glob("automations.yaml.divoom-backup-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    # the comment only survives in the backup, that is what it is for
    assert b"# Guten Morgen" in backups[0].read_bytes()
    assert b"# Guten Morgen" not in automations.read_bytes()


@pytest.mark.parametrize(
    "snippet,reason",
    [
        ("  token: !secret divoom_token\n", "secret"),
        ("  extra: !include divoom_extra.yaml\n", "include"),
        ("  token: !env_var DIVOOM_TOKEN\n", "env_var"),
        ("  <<: *shared\n", "merge_key"),
        ("  data: &shared\n", "anchor"),
    ],
)
async def test_migrate_refuses_files_it_would_damage(hass, config_dir, snippet, reason):
    automations = config_dir / "automations.yaml"
    automations.write_text(AUTOMATIONS_YAML + snippet, encoding="utf-8")
    original = automations.read_bytes()
    register_entry(hass)

    changed, converted, blocked = await async_migrate(hass)

    assert changed == []
    assert converted == 0
    assert blocked == {"automation": reason}
    assert automations.read_bytes() == original


def test_unsafe_reason_passes_ordinary_files():
    assert unsafe_reason(AUTOMATIONS_YAML) is None
    assert unsafe_reason(SCRIPTS_YAML) is None


async def test_a_failing_round_trip_check_writes_nothing(hass, yaml_files):
    automations, scripts = yaml_files
    originals = automations.read_bytes(), scripts.read_bytes()
    register_entry(hass)

    with patch.object(migration_module, "parse_yaml", return_value={"not": "what we meant"}):
        with pytest.raises(HomeAssistantError):
            await async_migrate(hass)

    assert (automations.read_bytes(), scripts.read_bytes()) == originals
    assert list(automations.parent.glob("*divoom-backup*")) == []


async def test_nothing_to_migrate_leaves_the_files_alone(hass, config_dir):
    automations = config_dir / "automations.yaml"
    automations.write_text(
        "- id: '1'\n  alias: X\n  actions:\n  - action: light.turn_on\n", encoding="utf-8"
    )
    original = automations.read_bytes()
    register_entry(hass)

    changed, converted, blocked = await async_migrate(hass)

    assert (changed, converted, blocked) == ([], 0, {})
    assert automations.read_bytes() == original


# --- scan and issue ---------------------------------------------------------


async def setup_automation(hass, config):
    assert await async_setup_component(hass, "automation", {"automation": config})
    await hass.async_block_till_done()


async def test_scan_finds_legacy_calls_in_automations(hass):
    register_entry(hass)
    await setup_automation(
        hass,
        [
            {
                "id": "abc",
                "alias": "Legacy One",
                "trigger": [],
                "action": [step("brightness", {"number": 10})],
            },
            {
                "id": "def",
                "alias": "Clean",
                "trigger": [],
                "action": [{"action": "light.turn_on", "entity_id": "light.x"}],
            },
        ],
    )

    result = async_scan(hass)

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.name == "Legacy One"
    assert finding.key == "abc"
    assert finding.calls == 1
    assert finding.writable
    assert finding.link == "/config/automation/edit/abc"


async def test_scan_does_not_mutate_the_live_config(hass):
    register_entry(hass)
    await setup_automation(
        hass,
        [{"id": "abc", "alias": "Legacy", "trigger": [], "action": [step("on", {})]}],
    )

    async_scan(hass)
    async_scan(hass)

    raw = list(hass.data[automation.DATA_COMPONENT].entities)[0].raw_config
    assert raw["action"][0]["action"] == "notify.divoom_test"


async def test_scan_flags_unconvertible_entries_as_manual(hass):
    register_entry(hass)
    await setup_automation(
        hass,
        [
            {
                "id": "abc",
                "alias": "Templated",
                "trigger": [],
                "action": [step("{{ states('input_text.mode') }}", {})],
            }
        ],
    )

    result = async_scan(hass)

    assert result.findings[0].reasons == [REASON_TEMPLATED_MODE]
    assert not result.findings[0].writable
    assert result.manual and not result.writable


async def test_scan_is_empty_without_a_config_entry(hass):
    await setup_automation(
        hass,
        [{"id": "abc", "alias": "Legacy", "trigger": [], "action": [step("on", {})]}],
    )

    assert async_scan(hass).findings == []


async def test_rescan_raises_and_clears_the_issue(hass):
    entry = register_entry(hass)
    await setup_automation(
        hass,
        [{"id": "abc", "alias": "Legacy", "trigger": [], "action": [step("on", {})]}],
    )
    registry = ir.async_get(hass)

    async_rescan(hass)
    issue = registry.async_get_issue(DOMAIN, ISSUE_LEGACY_NOTIFY)
    assert issue is not None
    assert issue.is_fixable
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_placeholders["count"] == "1"

    # with the device gone there is no notify.divoom_test left to call
    await hass.config_entries.async_remove(entry.entry_id)
    async_rescan(hass)

    assert registry.async_get_issue(DOMAIN, ISSUE_LEGACY_NOTIFY) is None


async def test_issue_strings_cover_every_flow_outcome(hass):
    """The flow can only show a step or abort with a reason that is translated."""
    strings = json.loads((COMPONENT_PATH / "strings.json").read_text(encoding="utf-8"))
    fix_flow = strings["issues"][ISSUE_LEGACY_NOTIFY]["fix_flow"]

    assert set(fix_flow["step"]) == {"init", "apply", "preview"}
    assert set(fix_flow["step"]["init"]["menu_options"]) == {"apply", "preview", "ignore"}
    assert set(fix_flow["abort"]) == {
        "issue_ignored",
        "manual_migration_required",
        "migration_failed",
        "nothing_to_do",
        "unsafe_file",
    }


@pytest.mark.parametrize("language", ["en", "de"])
async def test_issue_translations_are_reachable_for_the_frontend(hass, language):
    """The frontend looks the issue up by flattened key, so go through the real
    loader rather than the file: a block nested one level off still parses."""
    # resolving the integration proves the loader sees our translations folder
    integration = (await loader.async_get_custom_components(hass))[DOMAIN]
    assert integration.has_translations

    resources = await translation.async_get_translations(hass, language, "issues", [DOMAIN])

    prefix = "component.{0}.issues.{1}".format(DOMAIN, ISSUE_LEGACY_NOTIFY)
    strings = json.loads((COMPONENT_PATH / "strings.json").read_text(encoding="utf-8"))
    expected = {
        "{0}.{1}".format(prefix, key)
        for key in recursive_flatten("", strings["issues"][ISSUE_LEGACY_NOTIFY])
    }

    assert expected <= set(resources)
    assert resources["{0}.title".format(prefix)]
    assert resources["{0}.fix_flow.step.init.menu_options.apply".format(prefix)]


# --- the repair flow --------------------------------------------------------


async def start_flow(hass):
    flow = LegacyNotifyRepairFlow()
    flow.hass = hass
    flow.issue_id = ISSUE_LEGACY_NOTIFY
    return flow


async def test_flow_offers_the_menu_when_there_is_work(hass):
    register_entry(hass)
    await setup_automation(
        hass,
        [{"id": "abc", "alias": "Legacy", "trigger": [], "action": [step("on", {})]}],
    )
    flow = await start_flow(hass)

    result = await flow.async_step_init()

    assert result["type"] == "menu"
    assert result["menu_options"] == ["apply", "preview", "ignore"]
    assert result["description_placeholders"]["count"] == "1"


async def test_flow_aborts_when_nothing_is_left(hass):
    register_entry(hass)
    flow = await start_flow(hass)

    result = await flow.async_step_init()

    assert result["type"] == "abort"
    assert result["reason"] == "nothing_to_do"


async def test_flow_resolves_the_issue_when_everything_converted(hass, config_dir):
    """Nothing is left over after the rewrite, so the flow finishes and lets
    async_finish_flow drop the issue."""
    (config_dir / "automations.yaml").write_text(
        "- id: abc\n  alias: Legacy\n  actions:\n"
        "  - action: notify.divoom_test\n    data:\n      message: 'on'\n",
        encoding="utf-8",
    )
    register_entry(hass)
    # the loaded automation is already clean, only the file still is not, so
    # the rescan after the rewrite has nothing left to report
    await setup_automation(hass, [{"id": "abc", "alias": "Clean", "trigger": [], "action": []}])
    reload = async_mock_service(hass, "automation", "reload", schema=vol.Schema({}))
    flow = await start_flow(hass)

    result = await flow.async_step_apply({"confirm": True})

    assert result["type"] == "create_entry"
    assert len(reload) == 1
    assert "divoom.on" in (config_dir / "automations.yaml").read_text(encoding="utf-8")


async def test_flow_keeps_the_issue_when_manual_work_remains(hass, config_dir):
    (config_dir / "automations.yaml").write_text(
        "- id: abc\n  alias: Legacy\n  actions: []\n", encoding="utf-8"
    )
    register_entry(hass)
    await setup_automation(
        hass,
        [
            {
                "id": "abc",
                "alias": "Templated",
                "trigger": [],
                "action": [step("{{ x }}", {})],
            }
        ],
    )
    flow = await start_flow(hass)

    result = await flow.async_step_apply({"confirm": True})

    assert result["type"] == "abort"
    assert result["reason"] == "manual_migration_required"
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_LEGACY_NOTIFY) is not None


async def test_flow_apply_without_confirmation_returns_to_the_menu(hass):
    register_entry(hass)
    await setup_automation(
        hass,
        [{"id": "abc", "alias": "Legacy", "trigger": [], "action": [step("on", {})]}],
    )
    flow = await start_flow(hass)

    result = await flow.async_step_apply({"confirm": False})

    assert result["type"] == "menu"


async def test_flow_ignore_marks_the_issue_ignored(hass):
    register_entry(hass)
    await setup_automation(
        hass,
        [{"id": "abc", "alias": "Legacy", "trigger": [], "action": [step("on", {})]}],
    )
    async_rescan(hass)
    flow = await start_flow(hass)

    result = await flow.async_step_ignore()

    assert result["type"] == "abort"
    assert result["reason"] == "issue_ignored"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_LEGACY_NOTIFY)
    assert issue.dismissed_version is not None


async def test_flow_preview_shows_before_and_after(hass):
    register_entry(hass)
    await setup_automation(
        hass,
        [
            {
                "id": "abc",
                "alias": "Legacy",
                "trigger": [],
                "action": [step("brightness", {"number": 75})],
            }
        ],
    )
    flow = await start_flow(hass)

    result = await flow.async_step_preview()

    preview = result["description_placeholders"]["preview"]
    assert "notify.divoom_test" in preview
    assert "divoom.brightness" in preview
    assert "brightness: 75" in preview
