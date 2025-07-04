# hass-divoom
[![HACS Validation](https://github.com/d03n3rfr1tz3/hass-divoom/actions/workflows/hacs.yml/badge.svg)](https://github.com/d03n3rfr1tz3/hass-divoom/actions/workflows/hacs.yml)
[![Hassfest Validation](https://github.com/d03n3rfr1tz3/hass-divoom/actions/workflows/hassfest.yml/badge.svg)](https://github.com/d03n3rfr1tz3/hass-divoom/actions/workflows/hassfest.yml)
[![version](https://img.shields.io/github/manifest-json/v/d03n3rfr1tz3/hass-divoom?filename=custom_components%2Fdivoom%2Fmanifest.json)](https://github.com/d03n3rfr1tz3/hass-divoom/releases/latest)

**Divoom Integration for Home Assistant**

Allows you to send commands to your Divoom device through a Home Assistant notification service. It allows you to control your Divoom device
in your automations and scripts however you want. Currently no reading commands or sensors are implemented, because everything works through
a Notification Service. Just send controls/animations to your Divoom device through that Notification Service.

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
      - [MODE timer](#mode-timer)
      - [MODE visualization](#mode-visualization)
      - [MODE volume](#mode-volume)
      - [MODE weather](#mode-weather)
      - [YAML vs UI](#yaml-vs-ui)
    + [Examples per Device](#examples-per-device)
  * [Troubleshooting](#troubleshooting)
    + [Cannot connect](#cannot-connect)
    + [GIF does not work](#gif-does-not-work)
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
* `DIVOOM_DEVICE_PORT`: The port of your Divoom device. Typically its just `1`, but on some audio-supported devices it might be `2`.

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
* Choose a `port`. If you are unsure, first try `1`. If that doesn't work, try `2`.
* Select your device type (e.g. `pixoo`, `ditoo` and such)
* Click Send and then Finish

Beware that the UI configuration currently does not fully support my [Bluetooth Proxy for ESP32](https://github.com/d03n3rfr1tz3/esp32-divoom).
Currently it is supported through auto-discovery via ZeroConf, as well as through the UI configuration by setting the `host` option. It does not
add to the list of discovered Bluetooth devices, which means you have to manually type the MAC address in that case.

### Manual Configuration
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
  Currently `aurabox`, `backpack`, `ditoo`, `ditoomic`, `pixoo`, `pixoomax`, `timebox`, `timeboxmini` and `tivoo` are supported.
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

This custom component acts as a notify service. This means that the
Service Data requires a message parameter, which basically is the
command/mode we are sending to the device. Some commands/modes need
additional parameters, which should be provided in the service data
payload.

There was also an older style, where the message would be left empty
and the mode also passed in through the service data. It is still
supported as of today, but because it looks odd and confuses people,
it's not the preferred way anymore.

### Basic Modes
The general structure for all modes are similar, but each mode has different parameter. Below the example
of the basic structure, you can find a documentation of each mode.

Modern:
```yaml
service: notify.NOTIFIER_NAME
data:
  message: "MODE"
  data:
    parameter: value
```

Classic:
```yaml
service: notify.NOTIFIER_NAME
data:
  message: ""
  data:
    mode: "MODE"
    parameter: value
```

### Examples

#### MODE alarm
Sets an alarm. You might have to experiment with the options your Divoom device supports and what it actually changes. Unsupported values will be ignored or if possible directly zeroed by this component, to prevent strange behavior.

| Parameter | Description |
| ---       | ---         |
| `number`  | The concrete slot for the alarm. For the actual amount of slots you might have to look into the phone app. |
| `value`   | The concrete time for when the alarm should happen in the format `mm:ss`. |
| `weekday` | The typical list of weekdays for when the alarm should happen. |
| `alarmmode` | The alarm mode. Look into your phone app for what is supported by your Divoom device. |
| `triggermode` | The trigger mode. Look into your phone app for what is supported by your Divoom device. |
| `frequency` | The radio frequency to set. |
| `volume`  | The volume of the alarm. |

```
message: 'alarm'
data:
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

| Parameter | Description |
| ---       | ---         |
| `brightness` or `number` or `value` | The brightness value between 0 and 100. |

```
message: 'brightness'
data:
  brightness: 100
```

#### MODE clock
Shows the clock channel.

| Parameter | Description |
| ---       | ---         |
| `clock` | The style of the clock. Accepts a number between 0 and 9. <br/> `0` = Fullscreen, `1` = Rainbow, `2` = Boxed, `3` = Analog square, <br/> `4` = Fullscreen negative, `5` = Analog round, `6` = Widescreen |
| `twentyfour` | Changes between 12h or 24h format. <br/> `0` = 12h, `1` = 24h. Defaults to 24h. Doesn't actually change the current time. |
| `weather` | Actives or deactivates showing the weather with `0` or `1`. |
| `temp`    | Actives or deactivates showing the temperature with `0` or `1`. |
| `calendar` | Actives or deactivates showing the calendar date with `0` or `1`. |
| `color`   | The color of the clock. Accepts an array of RGB color values. |
| `hot`     | Actives or deactivates showing the slideshow of the best images with `0` or `1`, which is right next to the other boolean-like buttons in the app, but a completely separate command in the protocol |

```
message: 'clock'
data:
  clock: 1
  weather: 0
  temp: 0
  calendar: 1
  color: [250, 0, 0]
```

#### MODE connect
Explicitly connects to your configured Divoom device. Might be useful, if you just want to connect without changing anything. Typically the connection is opened automatically when using any mode.

```
message: 'connect'
data:
```

#### MODE countdown
Shows the countdown tool.

| Parameter | Description |
| ---       | ---         |
| `value`   | Controls the start/stop state. <br/> `0` = stop, `1` = start |
| `countdown` | The concrete countdown in the format `mm:ss`. |

```
message: 'countdown'
data:
  countdown: '01:30'
```

#### MODE datetime
Sets the datetime.

| Parameter | Description |
| ---       | ---         |
| `value`   | The date and time in the typical ISO datetime format. Leave it empty or null to just use the current date and time. |

```
message: 'datetime'
data:
  value: '2024-12-31 18:30:00'
```

#### MODE design
Shows the design channel.

| Parameter | Description |
| ---       | ---         |
| `number`  | The number of the concrete design. Ranging from 0-2 you can specify the design 1-3. |

```
message: 'design'
data:
  number: 2
```

#### MODE disconnect
Explicitly disconnects from your configured Divoom device. Might be useful, if you cannot connect with your Phone or other devices. Typically this component leaves the connection open to your Divoom device.

```
message: 'disconnect'
data:
```

#### MODE effects
Shows the effects channel.

| Parameter | Description |
| ---       | ---         |
| `number`  | The number of the concrete effect. Might differ for some Divoom devices. Look into your phone app and count them. |

```
message: 'effects'
data:
  number: 2
```

#### MODE equalizer
Starts the music equalizer.

| Parameter         | Description |
| ---               | ---         |
| `number`          | The number of the concrete equalizer. Look into your phone app and count them. |
| `audiomode`       | Actives or deactivates the original audio mode with `0` or `1`. |
| `backgroundmode`  | Actives or deactivates the background audio mode with `0` or `1`. |
| `streammode`      | Actives or deactivates the streaming audio mode with `0` or `1`. |

```
message: 'equalizer'
data:
  number: 2
  audiomode: 1
```

#### MODE game
Shows a game. It is theoretically possible to open games, that are not shown in your phone app, but they might not work very well.

| Parameter | Description |
| ---       | ---         |
| `value`   | The number of the concrete game. Depending on your device you may have different amount of games. Look into your phone app and count them. |

```
message: 'game'
data:
  value: 2
```

#### MODE gamecontrol
Sends controlling commands to the currently open game.

| Parameter | Description |
| ---       | ---         |
| `value`   | `0` or `go` = go, <br/> `1` or `left` = left, <br/> `2` or `right` = right, <br/> `3` or `up` = up, <br/> `4` or `bottom` = bottom, <br/> `5` or `ok` = ok |

```
message: 'gamecontrol'
data:
  value: 'go'
```

#### MODE image
Shows the a static or animated image.

| Parameter | Description |
| ---       | ---         |
| `file`    | Specifes the image file relative to the configured media_directory, that will be displayed. |

```
message: 'image'
data:
  file: 'ha16.gif'
```

#### MODE keyboard
Controls the keyboard LEDs specifically on the Ditoo.

| Parameter | Description |
| ---       | ---         |
| `value`   | Changes the keyboard LED effect. <br/> `-1` = previous effect, `0` = toggle on/off, `1` = next effect |

```
message: 'keyboard'
data:
  value: 1
```

#### MODE light
Shows the light channel.

| Parameter    | Description |
| ---          | ---         |
| `brightness` | The brightness value between 0 and 100. |
| `color`      | The color of the light. Accepts an array of RGB color values. |

```
message: 'light'
data:
  brightness: 75
  color: [250, 0, 0]
```

#### MODE lyrics
Shows the lyrics channel. Might not be supported by every Divoom device.

| Parameter | Description |
| ---       | ---         |
| `number`  | The number of the concrete visualization. Might differ for some Divoom devices. Look into your phone app and count them. |

```
message: 'lyrics'
data:
```

#### MODE memorial
Sets a memorial (reminder).

| Parameter | Description |
| ---       | ---         |
| `number`  | The concrete slot for the memorial. For the actual amount of slots you might have to look into the phone app. |
| `value`   | The date and time in the typical ISO datetime format (year will be ignored). |
| `text`    | Specifies the name of your memorial, as it will appear in the phone app (default: Home Assistant). Limited to 16 characters. |

```
message: 'memorial'
data:
  number: 0
  value: '2000-12-31 00:00:00'
  text: 'Happy New Year!'
```

#### MODE noise
Shows the noise meter.

| Parameter | Description |
| ---       | ---         |
| `value`   | Controls the start/stop state. <br/> `0` = stop, `1` = start |

```
message: 'noise'
data:
  value: 1
```

#### MODE off
Turn the display off, by setting the pixels to black, the brightness to 0 and also switching a specific `power`-flag to 0.

```
message: 'off'
data:
```

#### MODE on
Turn the display on, by setting the pixels to black, the brightness to 100 and also switching a specific `power`-flag to 1.
Because of the pixels still being black and no automatic way to go back to the previous shown mode, you should send another command (like MODE `clock`) afterwards.

```
message: 'on'
data:
```

#### MODE playstate
Sets the playstate for the currently played music. Only supported by Divoom devices with audio features.

| Parameter | Description |
| ---       | ---         |
| `value`   | Controls the play/pause state. <br/> `0` = pause, `1` = play |

```
message: 'playstate'
data:
  value: 1
```

#### MODE radio
Shows and plays the radio channel. Only supported by Divoom devices with the radio feature.

| Parameter | Description |
| ---       | ---         |
| `value`   | Controls the on/off state. <br/> `0` = off, `1` = on |
| `frequency` | The radio frequency to set. |

```
message: 'radio'
data:
  value: 1
  frequency: 100.3
```

#### MODE raw
Sends raw data to the Divoom device. Might be useful, if there is something wrong or not supported by the other modes.

| Parameter | Description |
| ---       | ---         |
| `raw`     | The bytes to send. |

```
message: 'raw'
data:
  raw: [0x74, 0x64]
```

#### MODE scoreboard
Shows the scoreboard channel or tool.

| Parameter | Description |
| ---       | ---         |
| `player1` | The score of player one to show. |
| `player2` | The score of player two to show. |

```
message: 'scoreboard'
data:
  player1: 2
  player2: 1
```

#### MODE signal
Shows the signal channel.

| Parameter | Description |
| ---       | ---         |
| `number`  | The number of the concrete signal. Look into your phone app and count them. |

```
message: 'signal'
data:
  number: 2
```

#### MODE sleep
Shows the sleep mode, which plays soothing sounds, optionally with a timer and light.

| Parameter    | Description |
| ---          | ---         |
| `value`      | Controls the start/stop state. <br/> `0` = stop, `1` = start |
| `time`       | The time in minutes after which to stop the sleep mode. Defaults to `120` when not provided. |
| `sleepmode`  | The sound effect to play. Check in the app how many options are available. Accepts a number. |
| `frequency`  | The radio frequency to set. |
| `volume`     | The volume value between 0 and 100. |
| `color`      | The color of the display. Accepts an array of RGB color values. |
| `brightness` | The brightness value between 0 and 100. |

```
message: 'sleep'
data:
  value: 1
  time: 30
  sleepmode: 4
  volume: 10
  color: [255, 255, 0]
  brightness: 50
```

#### MODE timer
Shows the timer tool.

| Parameter | Description |
| ---       | ---         |
| `value`   | Controls the start/stop state. <br/> `0` = stop, `1` = start |

```
message: 'timer'
data:
  value: 1
```

#### MODE visualization
Shows the visualization channel.

| Parameter | Description |
| ---       | ---         |
| `number`  | The number of the concrete visualization. Might differ for some Divoom devices. Look into your phone app and count them. |

```
message: 'visualization'
data:
  number: 2
```

#### MODE volume
Sets the volume. Only supported by Divoom devices with audio features.

| Parameter | Description |
| ---       | ---         |
| `volume` or `number` or `value` | The volume value between 0 and 100. |

```
message: 'volume'
data:
  volume: 75
```

#### MODE weather
Sets the weather.

| Parameter | Description |
| ---       | ---         |
| `value`   | The temperature in degree including the temperature type for celsius or fahrenheit. |
| `weather` | The actual type of the weather. <br/> `1` = clear, `3` = cloudy sky, `5` = thunderstorm, `6` = rain, `8` = snow, `9` = fog |

```
message: 'weather'
data:
  value: '25°C'
  weather: 6
```

#### YAML vs UI

Modern:
```yaml
service: notify.divoom_pixoo
data:
  message: "brightness"
  data:
    brightness: 75
```

Classic:
```yaml
service: notify.divoom_pixoo
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
Examples for Tivoo: [devices/tivoo.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/tivoo.txt) 

## Troubleshooting
### Cannot connect
Make sure, that you at least paired your Home Assistant device once to your Divoom device. Also make sure, that you have the correct MAC address.
Also make sure, that your Phone is not currently connected to your Divoom device, because some don't allow that many connections.

If it seems to connect, but looses connection the moment you use any mode, you might have chosen the wrong port. On Pixoo and other non-audio
devices, it's typically `port: 1`. But on audio devices, like the Tivoo or Ditoo, it might be `port: 2`.

### GIF does not work

The most common problem is, that the GIF does not have the correct size or format. The Divoom devices (and to some extend my code) are nitpicky in that case. Strangly enough the Divoom app lets you download GIFs, but these are typically in the size of 320x320 and not fitting your device.
Your GIF needs to be exactly the size of your Divoom screen (*16x16* in case of a Pixoo or similar sized device), *non-interlaced* and with a *global color palette*.

I can recommend resizing and converting your GIFs with GIMP. Of course other software might also work, depending on the export/format options. When resizing a GIF downloaded from the Divoom app with GIMP, you better choose no interpolation to not blur your GIF. When exporting with GIMP, make sure to mark the animation checkbox and don't mark the interlace checkbox. For a few more details and an example look into the following comment: https://github.com/d03n3rfr1tz3/hass-divoom/issues/19#issuecomment-1982059358

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
