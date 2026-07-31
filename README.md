# hass-divoom
[![HACS Validation](https://github.com/d03n3rfr1tz3/hass-divoom/actions/workflows/hacs.yml/badge.svg)](https://github.com/d03n3rfr1tz3/hass-divoom/actions/workflows/hacs.yml)
[![Hassfest Validation](https://github.com/d03n3rfr1tz3/hass-divoom/actions/workflows/hassfest.yml/badge.svg)](https://github.com/d03n3rfr1tz3/hass-divoom/actions/workflows/hassfest.yml)
[![version](https://img.shields.io/github/manifest-json/v/d03n3rfr1tz3/hass-divoom?filename=custom_components%2Fdivoom%2Fmanifest.json)](https://github.com/d03n3rfr1tz3/hass-divoom/releases/latest)

**Divoom Integration for Home Assistant**

Allows you to send commands to your Divoom device through Home Assistant actions. Every mode your device supports has its own action, like
`divoom.clock` or `divoom.light`, with all its parameters available in the UI. It allows you to control your Divoom device in your automations
and scripts however you want. Currently no reading commands or sensors are implemented, because everything works through actions. Just send
controls/animations to your Divoom device through them.

The older `notify.NOTIFIER_NAME` service still works exactly as before, so existing automations keep running. See
[Legacy: Notify Service](#legacy-notify-service).

## Table of Contents
  * [Requirements](#requirements)
      - [Bluetooth Proxy](#bluetooth-proxy)
      - [Bluetooth Hardware](#bluetooth-hardware)
      - [Bluetooth Pairing](#bluetooth-pairing)
  * [Installation](#installation)
    + [Easy Installation](#easy-installation)
    + [Manual Installation](#manual-installation)
  * [Configuration](#configuration)
    + [Easy Configuration](#easy-configuration)
    + [Manual Configuration](#manual-configuration)
  * [Usage](#usage)
    + [Basic Modes](#basic-modes)
    + [Examples](#examples)
      - [MODE alarm](#mode-alarm)
      - [MODE brightness](#mode-brightness)
      - [MODE clock](#mode-clock)
      - [MODE connect](#mode-connect)
      - [MODE countdown](#mode-countdown)
      - [MODE datetime](#mode-datetime)
      - [MODE design](#mode-design)
      - [MODE disconnect](#mode-disconnect)
      - [MODE effects](#mode-effects)
      - [MODE game](#mode-game)
      - [MODE gamecontrol](#mode-gamecontrol)
      - [MODE image](#mode-image)
      - [MODE keyboard](#mode-keyboard)
      - [MODE light](#mode-light)
      - [MODE lyrics](#mode-lyrics)
      - [MODE memorial](#mode-memorial)
      - [MODE noise](#mode-noise)
      - [MODE off](#mode-off)
      - [MODE on](#mode-on)
      - [MODE playstate](#mode-playstate)
      - [MODE radio](#mode-radio)
      - [MODE raw](#mode-raw)
      - [MODE scoreboard](#mode-scoreboard)
      - [MODE signal](#mode-signal)
      - [MODE sleep](#mode-sleep)
      - [MODE temperature](#mode-temperature)
      - [MODE text](#mode-text)
      - [MODE timer](#mode-timer)
      - [MODE visualization](#mode-visualization)
      - [MODE volume](#mode-volume)
      - [MODE weather](#mode-weather)
    + [Legacy: Notify Service](#legacy-notify-service)
      - [YAML vs UI](#yaml-vs-ui)
    + [Examples per Device](#examples-per-device)
  * [Troubleshooting](#troubleshooting)
    + [Cannot connect](#cannot-connect)
    + [GIF does not work](#gif-does-not-work)
  * [Development](#development)
    + [Running Tests](#running-tests)
  * [Credits](#credits)

## Requirements
For this component to actually have chance to work, it needs a Bluetooth Classic connection. Unlike Bluetooth Low Energy (BLE), Bluetooth Classic,
as the name already indicates, is a bit older. Therefore it brings some difficulties with it, which you might not expect, when you only know BLE
devices. One for example is that the Bluetooth Proxies from Home Assistant/ ESPHome do only support BLE and therefore cannot be used with this
component. Another one is the support in Python itself. While a Bluetooth Classic connection is supported natively by Python, the pairing process
is not. That's why you very likely have to do some manual work, if you somehow did not do it already.

#### Bluetooth Proxy
As an alternative for directly connecting your Home Assistant via Bluetooth to your Divoom device, you can use my [Bluetooth Proxy for ESP32](https://github.com/d03n3rfr1tz3/esp32-divoom).
With this you don't have to fiddle around with Bluetooth Pairing in your Home Assistant. It's currently still quite new, so there might be some minor issues here and there.
If you are using my Bluetooth Proxy for ESP32, you can skip the whole Bluetooth Hardware and Bluetooth Pairing parts of this documentation.

#### Bluetooth Hardware
Of course you need Bluetooth hardware for that. It does not matter if you use the integrated Bluetooth controller of a Raspberry Pi 3/4/5 or an
additional dongle. As long as it supports a classic Bluetooth connection via RFCOMM, you are good to go. When in doubt, just try it or have a
look at the following part of the Home Assistant documentation: https://www.home-assistant.io/integrations/bluetooth/

#### Bluetooth Pairing
As described above, you need to pair your Divoom device at least once to your Home Assistant device. After the pairing is done, this component
can connect to your Divoom device anytime it's needed, even after restarting your Home Assistant. You have multiple possibilities to pair your
Home Assistant to your Divoom device. The following commands can be used to pair your devices. Use them via SSH.

* `bluetoothctl` and then `pair DIVOOM_DEVICE_MAC` and optionally also `connect DIVOOM_DEVICE_MAC` \
OR
* `rfcomm connect HCI_DEVICE DIVOOM_DEVICE_MAC DIVOOM_DEVICE_PORT`

Choose what fits your Home Assistant installation or host system best. `bluetoothctl` is the more modern way and should be available even on
very basic HASS.io installations. `rfcomm` and maybe even `hciconfig hci0 up` beforehand is an older way. Obviously you have to fill in
some placeholders above.

* `HCI_DEVICE`: The id of your Bluetooth controller. Typically just `hci0`, especially if you are using integrated Raspberry Pi Bluetooth.
* `DIVOOM_DEVICE_MAC`: The MAC address of your Divoom device. You can either get it via the Divoom App or by scanning for it.
* `DIVOOM_DEVICE_PORT`: The port of your Divoom device. Typically its just `1`, but on some audio-supported devices, like the Timoo, Tivoo or Ditoo it might be `2`. Timebox Mini is also a special case with its `port: 4`.

## Installation
First we need to install the component. That can be done in two ways: Easy or Manual

### Easy Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=d03n3rfr1tz3&repository=hass-divoom&category=integration)

* Use HACS
* ...
* Profit

### Manual Installation

* Download the repository. If you know git, a clone is fine. If not,
  just download https://github.com/d03n3rfr1tz3/hass-divoom/archive/main.zip
  to get the most recent code in a ZIP file.
* Copy the corresponding content of the ZIP file into `custom_components\divoom` in your Home Assistant
  configuration directory.
* Create a directory named `pixelart` in your Home Assistant configuration directory,
  for images that you may want to display on your device.
* Optionally copy the content of the `pixelart` directory from the ZIP file

## Configuration
Second we need to enable/ configure the component. Again that can be done in two ways: Easy or Manual

### Easy Configuration

* Go to Integrations
* If there is an auto-discovered entry, you are lucky and can skip two steps
* Use `Add Integration` and Search for `Divoom`
* Choose your Divoom device from the list of discovered Bluetooth devices
* Choose a `port`. If you are unsure, first try `1`. If that doesn't work, try `2`, `4` or all the other digits.
* Select your device type (e.g. `pixoo`, `ditoo` and such)
* Click Send and then Finish

After that your device can be picked in every `divoom.*` action.

Beware that the UI configuration currently does not fully support my [Bluetooth Proxy for ESP32](https://github.com/d03n3rfr1tz3/esp32-divoom).
Currently it is supported through auto-discovery via ZeroConf, as well as through the UI configuration by setting the `host` option. It does not
add to the list of discovered Bluetooth devices, which means you have to manually type the MAC address in that case.

### Manual Configuration
This is the legacy way and only recommended, if the Easy Configuration does not work for you.
A device configured like this has no config entry and therefore cannot be picked in the
`divoom.*` actions. It is controlled through its `notify.NOTIFIER_NAME` service instead,
which is described in [Legacy: Notify Service](#legacy-notify-service).

This can be done by manually adding the following snippet to your `configuration.yaml`
and filling in the capitalized placeholders. You can create a notify service for every
Divoom device you have, therefore allowing you to add multiple of these snippets.

```yaml
notify:
  - name: NOTIFIER_NAME
    platform: divoom
    host: "PROXY_HOST_OR_IP"
    mac: "DIVOOM_DEVICE_MAC_ADDRESS"
    port: DIVOOM_DEVICE_PORT
    device_type: "DIVOOM_DEVICE_TYPE"
    media_directory: "pixelart"
    escape_payload: false
```

* `name` (Recommended): The name for the notify service.
* `host` (Optional): The host or IP of your ESP32 with flashed [Bluetooth Proxy](https://github.com/d03n3rfr1tz3/esp32-divoom).
  Beware, that an ESPHome BLE Proxy does not work, because Divoom is using Bluetooth Classic and not Bluetooth Low-Energy.
  Just leave it out, if you want your Home Assistant to directly connect via Bluetooth.
* `mac` (Required): The Bluetooth MAC address for the Divoom device.
* `port` (Optional): The Bluetooth channel for the Divoom device. Typically 1, but might be 2 for some devices with audio features.
* `device_type`: The concrete type of your Divoom device. \
  Currently `aurabox`, `backpack`, `ditoo`, `ditoomic`, `pixoo`, `pixoomax`, `timebox`, `timeboxmini`, `timoo` and `tivoo` are supported.
  If you have a different device, you might try one that's most similar to yours.
* `media_directory` (Required): A directory, relative to the configuration dir, containing image
  files in GIF format. The component will use these to display static or animated images on the device.
* `escape_payload` (Optional): Adds escaping of the payload, which might be important for some older Divoom devices with
  older firmware (afaik some old Timebox versions). Deactivated by default, because newer versions don't need that.

Here is an example how it could look like.
```yaml
notify:
  - name: Divoom Pixoo
    platform: divoom
    mac: "12:34:56:78:9A"
    port: 1
    device_type: "pixoo"
    media_directory: "pixelart"
    escape_payload: false
```

```yaml
notify:
  - name: Divoom Ditoo
    platform: divoom
    host: "192.168.0.123"
    mac: "12:34:56:78:9A"
    port: 2
    device_type: "ditoo"
    media_directory: "pixelart"
    escape_payload: false
```

## Usage

This custom component provides one action per mode of your Divoom device.
Every mode is its own action, so the UI shows you exactly which parameters
it has, which of them are required and what they mean.

### Basic Modes
The general structure for all modes are similar, but each mode has different parameter. Below the example
of the basic structure, you can find a documentation of each mode. Not all modes are supported across
all devices. If in doubt, look into your mobile app if your device even has the corresponding feature
and then look into the example files for your specific device.

```yaml
action: divoom.MODE
data:
  entry_id: YOUR_DIVOOM_DEVICE
  parameter: value
```

`entry_id` is required and picks the device you want to talk to. In the UI it is a dropdown listing
your configured Divoom devices, so you never type it by hand. `YOUR_DIVOOM_DEVICE` in the examples
below is just a placeholder for it. To get the actual value for a YAML automation, click the action
together in the UI and then switch that action to `Edit in YAML`.

If your device does not support the mode you are calling, the action fails with an error telling you
so, instead of silently doing nothing. Should you want an automation to carry on anyway, use the
`continue_on_error: true` option that Home Assistant offers on every action.

### Examples

#### MODE alarm
Sets an alarm. You might have to experiment with the options your Divoom device supports and what it actually changes. Unsupported values will be ignored or if possible directly zeroed by this component, to prevent strange behavior.

| Parameter     | Required | Description |
| ---           | :---:    | --- |
| `number`      |          | The concrete slot for the alarm. For the actual amount of slots you might have to look into the phone app. |
| `value`       |          | The concrete time for when the alarm should happen in the format `hh:mm`. The three-part format `hh:mm:ss` is accepted as well. Leave it empty to clear the slot. |
| `weekday`     |          | The typical list of weekdays for when the alarm should happen. |
| `alarmmode`   |          | The alarm mode. Look into your phone app for what is supported by your Divoom device. |
| `triggermode` |          | The trigger mode. Look into your phone app for what is supported by your Divoom device. |
| `frequency`   |          | The radio frequency to set. |
| `volume`      |          | The volume of the alarm. |

```yaml
action: divoom.alarm
data:
  entry_id: YOUR_DIVOOM_DEVICE
  number: 0
  value: '07:30'
  weekday:
    - mon
    - tue
    - wed
    - thu
    - fri
```

#### MODE brightness
Sets the brightness.

| Parameter    | Required | Description |
| ---          | :---:    | --- |
| `brightness` | ✔        | The brightness value between 0 and 100. |

```yaml
action: divoom.brightness
data:
  entry_id: YOUR_DIVOOM_DEVICE
  brightness: 100
```

#### MODE clock
Shows the clock channel. Be aware, that this mode is very limited on older device like Aurabox or Timebox Mini.

| Parameter    | Required | Description |
| ---          | :---:    | --- |
| `clock`      | ✔        | The style of the clock. Accepts a number starting from 0 up to what the Divoom device supports.<br/> Examples from Pixoo: `0` = Fullscreen, `1` = Rainbow, `2` = Boxed, `3` = Analog square, <br/> `4` = Fullscreen negative, `5` = Analog round, `6` = Widescreen |
| `twentyfour` |          | Changes between 12h or 24h format. <br/> `false` = 12h, `true` = 24h. |
| `weather`    |          | Actives or deactivates showing the weather with `true` or `false`. |
| `temp`       |          | Actives or deactivates showing the temperature with `true` or `false`. |
| `calendar`   |          | Actives or deactivates showing the calendar date with `true` or `false`. |
| `color`      |          | The color of the clock. Accepts an array of RGB color values. |
| `hot`        |          | Actives or deactivates showing the slideshow of the best images with `true` or `false`, which is right next to the other boolean-like buttons in the app, but a completely separate command in the protocol |

```yaml
action: divoom.clock
data:
  entry_id: YOUR_DIVOOM_DEVICE
  clock: 1
  weather: false
  temp: false
  calendar: true
  color: [250, 0, 0]
```

#### MODE connect
Explicitly connects to your configured Divoom device. Might be useful, if you just want to connect without changing anything. Typically the connection is opened automatically when using any mode.

```yaml
action: divoom.connect
data:
  entry_id: YOUR_DIVOOM_DEVICE
```

#### MODE countdown
Shows the countdown tool.

| Parameter   | Required | Description |
| ---         | :---:    | --- |
| `value`     | ✔        | Controls the start/stop state. <br/> `false` = stop, `true` = start |
| `countdown` |          | The concrete countdown in the format `mm:ss`. <br/> Given as `hh:mm:ss`, the hours are ignored. |

```yaml
action: divoom.countdown
data:
  entry_id: YOUR_DIVOOM_DEVICE
  countdown: '01:30'
  value: true
```

#### MODE datetime
Sets the datetime.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `value`   |          | The date and time in the typical ISO datetime format. Leave it empty or null to just use the current date and time. |

```yaml
action: divoom.datetime
data:
  entry_id: YOUR_DIVOOM_DEVICE
  value: '2024-12-31 18:30:00'
```

#### MODE design
Shows the design channel.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `number`  | ✔        | The number of the concrete design. Accepts a number starting from 0 up to what the Divoom device supports.<br/> Examples from Pixoo: `0`-`2` for the designs 1-3 |

```yaml
action: divoom.design
data:
  entry_id: YOUR_DIVOOM_DEVICE
  number: 2
```

#### MODE disconnect
Explicitly disconnects from your configured Divoom device. Might be useful, if you cannot connect with your Phone or other devices. Typically this component leaves the connection open to your Divoom device.

```yaml
action: divoom.disconnect
data:
  entry_id: YOUR_DIVOOM_DEVICE
```

#### MODE effects
Shows the effects channel.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `number`  | ✔        | The number of the concrete effect. Might differ for some Divoom devices. Look into your phone app and count them. |

```yaml
action: divoom.effects
data:
  entry_id: YOUR_DIVOOM_DEVICE
  number: 2
```

#### MODE equalizer
Starts the music equalizer.

| Parameter        | Required | Description |
| ---              | :---:    | --- |
| `number`         | ✔        | The number of the concrete equalizer. Look into your phone app and count them. |
| `audiomode`      |          | Actives or deactivates the original audio mode with `true` or `false`. |
| `backgroundmode` |          | Actives or deactivates the background audio mode with `true` or `false`. |
| `streammode`     |          | Actives or deactivates the streaming audio mode with `true` or `false`. |

```yaml
action: divoom.equalizer
data:
  entry_id: YOUR_DIVOOM_DEVICE
  number: 2
  audiomode: true
```

#### MODE game
Shows a game. It is theoretically possible to open games, that are not shown in your phone app, but they might not work very well.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `value`   |          | The number of the concrete game. Depending on your device you may have different amount of games. Look into your phone app and count them. |

```yaml
action: divoom.game
data:
  entry_id: YOUR_DIVOOM_DEVICE
  value: 2
```

#### MODE gamecontrol
Sends controlling commands to the currently open game.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `value`   | ✔        | `go` = go, <br/> `left` = left, <br/> `right` = right, <br/> `up` = up, <br/> `down` = down, <br/> `ok` = ok |

```yaml
action: divoom.gamecontrol
data:
  entry_id: YOUR_DIVOOM_DEVICE
  value: 'go'
```

#### MODE image
Shows a static or animated image.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `file`    | ✔        | Specifes the image file relative to the configured media_directory, that will be displayed. |
| `time`    |          | The time in milliseconds between each frame. Defaults to timing of the GIF if omitted. |

```yaml
action: divoom.image
data:
  entry_id: YOUR_DIVOOM_DEVICE
  file: 'ha16.gif'
```

#### MODE keyboard
Controls the keyboard LEDs specifically on the Ditoo.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `value`   | ✔        | Changes the keyboard LED effect. <br/> `previous` = previous effect, <br/> `toggle` = toggle on/off, <br/> `next` = next effect |

```yaml
action: divoom.keyboard
data:
  entry_id: YOUR_DIVOOM_DEVICE
  value: 'next'
```

#### MODE light
Shows the light channel. Be aware, that this mode is very limited on the Aurabox, because it only supports 8 colors.

| Parameter    | Required | Description |
| ---          | :---:    | --- |
| `brightness` | ✔        | The brightness value between 0 and 100. |
| `color`      |          | The color of the light. Accepts an array of RGB color values. Leave it empty to fade through the colors. |

```yaml
action: divoom.light
data:
  entry_id: YOUR_DIVOOM_DEVICE
  brightness: 75
  color: [250, 0, 0]
```

#### MODE lyrics
Shows the lyrics channel. Might not be supported by every Divoom device.

```yaml
action: divoom.lyrics
data:
  entry_id: YOUR_DIVOOM_DEVICE
```

#### MODE memorial
Sets a memorial (reminder).

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `number`  |          | The concrete slot for the memorial. For the actual amount of slots you might have to look into the phone app. |
| `value`   |          | The date and time in the typical ISO datetime format (year will be ignored). Leave it empty to clear the slot. |
| `text`    |          | Specifies the name of your memorial, as it will appear in the phone app (default: Home Assistant). Limited to 16 characters. |

```yaml
action: divoom.memorial
data:
  entry_id: YOUR_DIVOOM_DEVICE
  number: 0
  value: '2000-12-31 00:00:00'
  text: 'Happy New Year!'
```

#### MODE noise
Shows the noise meter.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `value`   | ✔        | Controls the start/stop state. <br/> `false` = stop, `true` = start |

```yaml
action: divoom.noise
data:
  entry_id: YOUR_DIVOOM_DEVICE
  value: true
```

#### MODE off
Turn the display off, by setting the pixels to black, the brightness to 0 and also switching a specific `power`-flag to 0.

```yaml
action: divoom.off
data:
  entry_id: YOUR_DIVOOM_DEVICE
```

#### MODE on
Turn the display on, by setting the pixels to black, the brightness to 100 and also switching a specific `power`-flag to 1.
Because of the pixels still being black and no automatic way to go back to the previous shown mode, you should send another command (like MODE `clock`) afterwards.

```yaml
action: divoom.on
data:
  entry_id: YOUR_DIVOOM_DEVICE
```

#### MODE playstate
Sets the playstate for the currently played music. Only supported by Divoom devices with audio features.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `value`   | ✔        | Controls the play/pause state. <br/> `false` = pause, `true` = play |

```yaml
action: divoom.playstate
data:
  entry_id: YOUR_DIVOOM_DEVICE
  value: true
```

#### MODE radio
Shows and plays the radio channel. Only supported by Divoom devices with the radio feature.

| Parameter   | Required | Description |
| ---         | :---:    | --- |
| `value`     | ✔        | Controls the on/off state. <br/> `false` = off, `true` = on |
| `frequency` |          | The radio frequency to set. |

```yaml
action: divoom.radio
data:
  entry_id: YOUR_DIVOOM_DEVICE
  value: true
  frequency: 100.3
```

#### MODE raw
Sends raw data to the Divoom device. Might be useful, if there is something wrong or not supported by the other modes.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `raw`     | ✔        | The bytes to send. |

```yaml
action: divoom.raw
data:
  entry_id: YOUR_DIVOOM_DEVICE
  raw: [0x74, 0x64]
```

#### MODE scoreboard
Shows the scoreboard channel or tool.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `player1` |          | The score of player one to show. |
| `player2` |          | The score of player two to show. |

```yaml
action: divoom.scoreboard
data:
  entry_id: YOUR_DIVOOM_DEVICE
  player1: 2
  player2: 1
```

#### MODE signal
Shows the signal channel specifically on the Backpack.
It shows traffic signals, like a turn signal.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `number`  | ✔        | The number of the concrete signal. Look into your phone app and count them. |

```yaml
action: divoom.signal
data:
  entry_id: YOUR_DIVOOM_DEVICE
  number: 2
```

#### MODE sleep
Shows the sleep mode, which plays soothing sounds, optionally with a timer and light.

| Parameter    | Required | Description |
| ---          | :---:    | --- |
| `value`      | ✔        | Controls the start/stop state. <br/> `false` = stop, `true` = start |
| `time`       |          | The time in minutes after which to stop the sleep mode. Defaults to `120` when not provided. |
| `sleepmode`  |          | The sound effect to play. Check in the app how many options are available. Accepts a number. |
| `frequency`  |          | The radio frequency to set. |
| `volume`     |          | The volume value between 0 and 100. |
| `color`      |          | The color of the display. Accepts an array of RGB color values. |
| `brightness` |          | The brightness value between 0 and 100. |

```yaml
action: divoom.sleep
data:
  entry_id: YOUR_DIVOOM_DEVICE
  value: true
  time: 30
  sleepmode: 4
  volume: 10
  color: [255, 255, 0]
  brightness: 50
```

#### MODE temperature
Shows the temperature channel. Be aware, that this mode is specifically for Aurabox or Timebox Mini. It still works on other device, but utilizes the `clock` mode and therefore might change settings unintentional.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `value`   | ✔        | Changes between °C or °F unit. |
| `color`   |          | The color of the temperature. Accepts an array of RGB color values. |

```yaml
action: divoom.temperature
data:
  entry_id: YOUR_DIVOOM_DEVICE
  value: '°C'
  color: [250, 0, 0]
```

#### MODE text
Shows text as a scrolling animation. Font can be any TrueType or OpenType font installed on the system or placed into the `fonts`-folder. The following fonts are included: `arcade.ttf`, `arial.ttf`, `divoom.ttf`, `impact.ttf` and `pixelpowerline.ttf`. Be aware, that a longer text or wide font might not fit into the frame limitation of ~60 frames.

| Parameter          | Required | Description |
| ---                | :---:    | --- |
| `text`             | ✔        | The text that will be animated. |
| `font`             |          | The font name or filename of the font that should be used. Defaults to a generic font. |
| `size`             |          | The font size in pixels. Defaults to the screen size of the device. |
| `time`             |          | The time in milliseconds between each frame. Defaults to 100ms per frame. |
| `foreground_color` |          | The color of the text alone. Accepts an array of RGB color values. Defaults to white. |
| `background_color` |          | The color of the background alone. Accepts an array of RGB color values. Defaults to black. |

```yaml
action: divoom.text
data:
  entry_id: YOUR_DIVOOM_DEVICE
  text: 'Hi Divoom'
  font: 'divoom.ttf'
  foreground_color: [250, 0, 0]
  background_color: [0, 0, 0]
```

#### MODE timer
Shows the timer tool.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `value`   | ✔        | Controls the start/stop state. <br/> `false` = stop, `true` = start |

```yaml
action: divoom.timer
data:
  entry_id: YOUR_DIVOOM_DEVICE
  value: true
```

#### MODE visualization
Shows the visualization channel. The Divoom Backpack does not support this mode, because it has no microphone. Use the `signal` mode there instead.

| Parameter          | Required | Description |
| ---                | :---:    | --- |
| `number`           | ✔        | The number of the concrete visualization. Might differ for some Divoom devices. Look into your phone app and count them. |
| `foreground_color` |          | The color of the foreground alone. Accepts an array of RGB color values. Only supported by the oldest devices. |
| `background_color` |          | The color of the background alone. Accepts an array of RGB color values. Only supported by the oldest devices. |

```yaml
action: divoom.visualization
data:
  entry_id: YOUR_DIVOOM_DEVICE
  number: 2
  foreground_color: [250, 0, 0]
  background_color: [0, 0, 0]
```

#### MODE volume
Sets the volume. Only supported by Divoom devices with audio features.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `volume`  | ✔        | The volume value between 0 and 100. |

```yaml
action: divoom.volume
data:
  entry_id: YOUR_DIVOOM_DEVICE
  volume: 75
```

#### MODE weather
Sets the weather.

| Parameter | Required | Description |
| ---       | :---:    | --- |
| `value`   | ✔        | The temperature in degree, optionally including the temperature type for celsius or fahrenheit as `°C` or `°F`. |
| `unit`    |          | The temperature type for celsius or fahrenheit as `°C` or `°F`. Takes precedence over the type given in `value`. Without any type the device keeps its current one. |
| `weather` |          | The actual type of the weather. <br/> `1` = clear, `3` = cloudy sky, `5` = thunderstorm, `6` = rain, `8` = snow, `9` = fog. <br/> The Home Assistant weather states (`sunny`, `rainy`, `partlycloudy`, ...) are accepted as well. |

```yaml
action: divoom.weather
data:
  entry_id: YOUR_DIVOOM_DEVICE
  value: '25°C'
  weather: 6
```

### Legacy: Notify Service

Before the actions existed, everything went through a notify service named after your device.
That way still works and is not going away, so existing automations and scripts keep running
unchanged. It is also the only way to control a device from the [Manual Configuration](#manual-configuration),
because such a device has no config entry to pick.

The parameters are the same ones documented for each mode above, only the wrapping differs: the
mode moves into `message` and the parameters move into a nested `data`.

```yaml
action: notify.NOTIFIER_NAME
data:
  message: "MODE"
  data:
    parameter: value
```

There is also an older style, where the message is left empty and the mode is passed in through
the service data as well. It is still supported as of today, but because it looks odd and confuses
people, it's not the preferred way anymore.

```yaml
action: notify.NOTIFIER_NAME
data:
  message: ""
  data:
    mode: "MODE"
    parameter: value
```

A few more differences to the actions:

* The notify service additionally accepts some alternative spellings: `number` or `value` instead
  of `brightness` and `volume`, and the combined `color: [[foreground], [background]]` instead of
  `foreground_color` and `background_color`.
* Where the actions want a word, it also takes the raw protocol number: `-1`, `0` or `1` for the
  keyboard effect, `0` to `5` for the game control and `0` or `1` instead of `°C` or `°F`.
* It does not validate your parameters. A value out of range is passed to the device as it is.
* A mode your device does not support only produces a warning in the log. It does not fail, so an
  automation using it just carries on.

#### YAML vs UI

Modern:
```yaml
action: notify.divoom_pixoo
data:
  message: "brightness"
  data:
    brightness: 75
```

Classic:
```yaml
action: notify.divoom_pixoo
data:
  message: ""
  data:
    mode: "brightness"
    brightness: 75
```

UI: \
![screenshot](https://github.com/d03n3rfr1tz3/hass-divoom/assets/1483070/f5ec0e0e-183b-4ba9-956f-21aa67bcc9c1)

### Examples per Device
You can find more examples for each mode and all supported devices in separate files: \
Examples for Aurabox: [devices/aurabox.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/aurabox.txt) \
Examples for Backpack: [devices/backpack.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/backpack.txt) \
Examples for Ditoo: [devices/ditoo.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/ditoo.txt) \
Examples for Ditoo Mic: [devices/ditoomic.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/ditoomic.txt) \
Examples for Pixoo: [devices/pixoo.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/pixoo.txt) \
Examples for Pixoo Max: [devices/pixoomax.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/pixoomax.txt) \
Examples for Timebox: [devices/timebox.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/timebox.txt) \
Examples for Timebox Mini: [devices/timeboxmini.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/timeboxmini.txt) \
Examples for Timoo: [devices/timoo.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/timoo.txt) \
Examples for Tivoo: [devices/tivoo.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/tivoo.txt) 

## Troubleshooting
### Cannot connect
Make sure, that you at least paired your Home Assistant device once to your Divoom device. Also make sure, that you have the correct MAC address.
Also make sure, that your Phone is not currently connected to your Divoom device, because some don't allow that many connections.

If it seems to connect, but looses connection the moment you use any mode, you might have chosen the wrong port. On Pixoo and other non-audio
devices, it's typically `port: 1`. But on audio devices, like the Timoo, Tivoo or Ditoo, it might be `port: 2`. Timebox Mini is also a special case with its `port: 4`.

### GIF does not work

The most common problem is, that the GIF does not have the correct size or format. The Divoom devices (and to some extend my code) are nitpicky in that case. Strangly enough the Divoom app lets you download GIFs, but these are typically in the size of 320x320 and not fitting your device.
Your GIF needs to be exactly the size of your Divoom screen (*16x16* in case of a Pixoo or similar sized device), *non-interlaced* and with a *global color palette*.

I can recommend resizing and converting your GIFs with GIMP. Of course other software might also work, depending on the export/format options. When resizing a GIF downloaded from the Divoom app with GIMP, you better choose no interpolation to not blur your GIF. When exporting with GIMP, make sure to mark the animation checkbox and don't mark the interlace checkbox. For a few more details and an example look into the following comment: https://github.com/d03n3rfr1tz3/hass-divoom/issues/19#issuecomment-1982059358

## Development
### Running Tests
Open a terminal in the repository's root folder before running the commands below.
Requires Python 3.14 or newer, since that's what the Home Assistant version behind
`pytest-homeassistant-custom-component` in `tests/requirements_test.txt` needs.

The second step resolves the requirements that Home Assistant itself pins for the components
this integration imports, straight from the manifests of the installed HA version. The
resulting `requirements_ha.txt` is generated.

bash/Linux/macOS:
```bash
pip install -r tests/requirements_test.txt
python tests/gen_requirements.py --output requirements_ha.txt
pip install -r requirements_ha.txt
PYTHONPATH=tests pytest tests
```

PowerShell (Windows):
```powershell
pip install -r tests/requirements_test.txt
python tests/gen_requirements.py --output requirements_ha.txt
pip install -r requirements_ha.txt
$env:PYTHONPATH = "tests"
pytest tests
```

## Credits
A lot of the bluetooth communication with the Divoom device is based on gathering information from multiple sources, that already
reverse engineered an older or different Divoom device. Only because of this, I could reverse engineer more commands myself. Therefore
credit goes to the following owners and git repos (you are the heroes here):

https://github.com/RomRider/node-divoom-timebox-evo/ (especially for the [protocol documentation](https://github.com/RomRider/node-divoom-timebox-evo/blob/master/PROTOCOL.md))  
https://github.com/mumpitzstuff/fhem-Divoom  
https://github.com/ScR4tCh/timebox/  
https://bitbucket.org/pjhardy/homeassistant-timebox/src/master/

Also thanks to whoever made the following (official?) documentation of most of the Divoom protocol. Even while it does not have the latest
commands available in the Ditoo, it still helped a lot in refining and completing stuff. \
https://docin.divoom-gz.com/web/#/5/146
