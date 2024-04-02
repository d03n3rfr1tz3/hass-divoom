# hass-divoom
[![HACS Validation](https://github.com/d03n3rfr1tz3/hass-divoom/actions/workflows/hacs.yml/badge.svg)](https://github.com/d03n3rfr1tz3/hass-divoom/actions/workflows/hacs.yml)
[![Hassfest Validation](https://github.com/d03n3rfr1tz3/hass-divoom/actions/workflows/hassfest.yml/badge.svg)](https://github.com/d03n3rfr1tz3/hass-divoom/actions/workflows/hassfest.yml)
[![version](https://img.shields.io/github/manifest-json/v/d03n3rfr1tz3/hass-divoom?filename=custom_components%2Fdivoom%2Fmanifest.json)](https://github.com/d03n3rfr1tz3/hass-divoom/releases/latest)

**Divoom Integration for Home Assistant**

Allows you to send commands to your Divoom device through a Home Assistant notification service. It allows you to control your Divoom device
in your automations and scripts however you want. Currently no reading commands or sensors are implemented, because everything works through
a Notification Service. Just send controls/animations to your Divoom device through that Notification Service.

## Credits
First of, a lot of the bluetooth communication with the Divoom device (only tested on my Pixoo and Ditoo for now) is based on gathering information from multiple sources,
that already reverse engineered an older or different Divoom device. Only because of this, I could reverse engineer more commands myself. Therefore credit
goes to the following owners and git repos (you are the heroes here):

https://github.com/RomRider/node-divoom-timebox-evo/ (especially for the [protocol documentation](https://github.com/RomRider/node-divoom-timebox-evo/blob/master/PROTOCOL.md))  
https://github.com/mumpitzstuff/fhem-Divoom  
https://github.com/ScR4tCh/timebox/  
https://bitbucket.org/pjhardy/homeassistant-timebox/src/master/

Also thanks to whoever made the following (official?) documentation of most of the Divoom protocol. Even while it does not have the latest
commands available in the Ditoo, it still helped a lot in refining and completing stuff. \
https://docin.divoom-gz.com/web/#/5/146

## Documentation
Further documentation besides the steps and examples below may follow. For now I'm happy that it works and that the HACS integration might be quite close! 😁

### Install the custom component
First we need to install the component. That can be done in two ways: Easy or Manual

#### Easy Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=d03n3rfr1tz3&repository=hass-divoom&category=integration)

* Use HACS
* ...
* Profit

#### Manual Installation

* Download the repository. If you know git, a clone is fine. If not,
  just download https://github.com/d03n3rfr1tz3/hass-divoom/archive/main.zip
  to get the most recent code in a ZIP file.
* Copy the corresponding content of the ZIP file into `custom_components\divoom` in your Home Assistant
  configuration directory.
* Create a directory named `pixelart` in your Home Assistant configuration directory,
  for images that you may want to display on your device.
* Optionally copy the content of the `pixelart` directory from the ZIP file

### Enable the custom component
Second we need to configure the component. Again that can be done in two ways: Easy or Manual

#### Easy Configuration

* Go to Integrations
* If there is an auto-discovered entry, you are lucky and can skip two steps
* Use `Add Integration` and Search for `Divoom`
* Choose your Divoom device from the list of discovered bluetooth devices
* Choose a `port`. If you are unsure, first try `1`. If that doesn't work, try `2`.
* Select your device type (e.g. `pixoo`, `ditoo` and such)
* Click Send and then Finish

#### Manual Configuration
This can be done by manually adding the following snippet to your `configuration.yaml`
and filling in the capitalized placeholders. You can create a notify service for every
Divoom device you have, therefore allowing you to add multiple of these snippets.

```yaml
notify:
  - name: NOTIFIER_NAME
    platform: divoom
    mac: "DIVOOM_DEVICE_MAC_ADDRESS"
    port: DIVOOM_DEVICE_PORT
    device_type: "DIVOOM_DEVICE_TYPE"
    media_directory: "pixelart"
    escape_payload: false
```

* name (Recommended): The name for the notify service.
* mac (Required): The Bluetooth MAC address for the Divoom device.
* port (Optional): The Bluetooth channel for the Divoom device. Typically 1, but might be 2 for some devices with audio features.
* device_type: The concrete type of your Divoom device. Currently `pixoo`, `pixoomax`, `timebox`, `tivoo`, `ditoo` are supported.
* media_directory (Required): A directory, relative to the configuration dir, containing image
  files in GIF format. The component will use these to display static or animated images on the device.
* escape_payload (Optional): Adds escaping of the payload, which might be important for some older Divoom devices with
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

### Usage

This custom component acts as a notify service. This means that the
Service Data requires a message parameter, which basically is the
command/mode we are sending to the device. Some commands/modes need
additional parameters, which should be provided in the service data
payload.

There was also an older style, where the message would be left empty
and the mode also passed in through the service data. It is still
supported as of today, but because it looks odd and confuses people,
it's not the preferred way anymore.

#### Basic display modes

Modern:
```yaml
service: notify.NOTIFIER_NAME
data:
  message: "MODE"
  data:
```

Classic:
```yaml
service: notify.NOTIFIER_NAME
data:
  message: ""
  data:
    mode: "MODE"
```

`MODE` on all currently supported Divoom devices can be one of:

* `clock`: Display the built-in clock channel. You can specify the style in the `clock` parameter.
  This mode also accepts the boolean-like parameters `weather`, `temp`, `calendar` and `hot` for activating the corresponding features.
  It's also possible to specify the `color` of the clock.
  * `clock` parameter accepts a number between 0 and 9. The actual supported clock styles depend on your device.\
    0 = Fullscreen, 1 = Rainbow, 2 = Boxed, 3 = Analog square,\
    4 = Fullscreen negative, 5 = Analog round, 6 = Widescreen
  * `hot` parameter controls the slideshow of the best images while in `clock` mode,
    which is right next to the other boolean-like buttons in the app, but a completely separate command in the protocol.
* `light`: Display the built-in light channel.
  It's also possible to specify the `brightness` and `color` of the light.
* `effects`: Display the built-in effects channel. With the parameter `number` you can
  specify the concrete effect. Look into your phone app and count them.
* `visualization`: Display the built-in visualization channel. With the parameter `number` you can
  specify the concrete effect. Look into your phone app and count them.
* `design`: Display the custom design channel. With the parameter `number` (ranging from 0-2) you can
  specify the concrete design 1-3.
* `scoreboard`: Display the built-in scoreboard channel. With the parameters `player1` and `player2` you can specify the displayed score.
* `image`: Display an animated or static image. The parameter `file` specifes the image file relative
  to the configured media_directory, that will be displayed.
  
* `game`: Display one of the built-in games. With the `value` parameter you can choose which game you want to open.
  Depending on your device you may have different amount of games.
* `gamecontrol`: Sends controls specified with the `value` parameter to the currently open game. \
  0 or 'go' = go, 1 or 'left' = left, 2 or 'right' = right, 3 or 'up' = up, 4 or 'bottom' = bottom, 5 or 'ok' = ok
* `brightness`: Sets the brightness using the `brightness` or `number` or `value` parameter.
* `datetime`: Sets the date and time using the `value` parameter in the typical ISO datetime format.
* `weather`: Sets the weather. Set the temperature using the `value` parameter and the weather type using the `weather` parameter.\
  1 = clear, 3 = cloudy sky, 5 = thunderstorm, 6 = rain, 8 = snow, 9 = fog

* `noise`: Shows the noise meter. You can control the start/stop state using the `value` parameter. \
  0 = stop, 1 = start
* `countdown`: Shows the countdown using the `countdown` parameter (format mm:ss). You can control the start/stop state using the `value` parameter. \
  0 = stop, 1 = start
* `timer`: Shows the timer. You can control the start/stop state using the `value` parameter. \
  0 = pause, 1 = start, 2 = reset
* `alarm`: Sets an alarm in the slot specified by the `number` parameter. With the `value` (format hh:mm) and `weekday` parameters you set when the alarm should go off and if it should repeat or just do it once. \
  With `alarmmode`, `triggermode`, `frequency` and `volume` you can set additional options on your alarm corresponding to what the Divoom app supports on your device. You might have to experiment
  with the options your Divoom device supports and what it actually changes. Unsupported values will be ignored or if possible directly zeroed by this component, to prevent strange behavior.
* `memorial`: Sets a memorial in the slot specified by the `number` parameter. With the `value` parameter in the typical ISO datetime format (year will be ignored) you set when the memorial should go off. \
  With the `text` parameter you can specify the name of your memorial, as it will appear in the app (default: Home Assistant).

* `raw`: Send a raw command using the `raw` parameter to the Divoom device.
  Might be useful, if a certain mode/feature is not implemented by this component yet.
* `connect`: Connects to the Divoom device. Might be useful, if you just want to connect without changing anything.
  Typically the connection is opened automatically when using any mode.
* `disconnect`: Disconnects from the Divoom device. Might be useful, if you cannot connect with your Phone or other devices.
  Typically this component leaves the connection open to your Divoom device.
* `on`: Turn the display on.
* `off`: Turn the display off.

`MODE` on some Divoom devices like TimeboxEvo, Tivoo and Ditoo additionally support:

* `lyrics`: Display the built-in the lyrics channel.
* `playstate`: Sets the play/pause state using the `value` parameter.
* `radio`: Shows the radio using the `value` parameter. Additionally the `frequency` can be set.
* `volume`: Sets the volume using the `volume` or `number` or `value` parameter.

`MODE` on Ditoo additionally support:

* `keyboard`: Changes the keyboard effects using the `value` parameter. \
  -1 = previous effect, 0 = toggle on/off, 1 = next effect

### Examples

An example from my own automation.

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

You can find more examples for each mode and all supported devices in separate files: \
Examples for Pixoo: [devices/pixoo.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/pixoo.txt) \
Examples for Pixoo Max: [devices/pixoomax.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/pixoomax.txt) \
Examples for Timebox: [devices/timebox.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/timebox.txt) \
Examples for Tivoo: [devices/tivoo.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/tivoo.txt) \
Examples for Ditoo: [devices/ditoo.txt](https://github.com/d03n3rfr1tz3/hass-divoom/blob/main/custom_components/divoom/devices/ditoo.txt)

### Bluetooth
#### Bluetooth interface

This component automatically connects to your Divoom device based on the configured MAC address. The only thing you sometimes have to prepare, is pairing it once to your Home Assistant device (for example your raspberry pi). Depending on your setup, that might be an easy or quite complicated task. After the pairing is done, this component can connect to your Divoom device anytime it's needed, even after restarting your Home Assistant. Newer versions of Home Assistant very likely already have Bluetooth enabled and configured somehow, so you might be lucky and skip a bunch of these steps. Older versions needed more manual steps to make it work.

You can get the MAC address using your Phones Bluetooth settings or from your Divoom app. When trying to pair the devices, you will probably use tools, that are also capable of scanning. Therefore you can also get the MAC address that way.

#### Bluetooth preparation

**Short version**: With the Divoom device turned on and looking for a Bluetooth connection, run the following through SSH to the host system (supervised installation). If your are using hass.io, I'm not sure how to pair the device.

```
sudo hciconfig hci0 up
sudo hcitool scan
```

This should eventually find the device, and print its MAC address.
Keep a note of this address, because you need to replace `MAC_ADDRESS` with it now.
If you already know the MAC address, you can directly skip to the next command.

```
sudo rfcomm connect hci0 MAC_ADDRESS 1
```

This should connect your Home Assistant device to your Divoom device including an initial pairing. This is only needed once.

**Long version**: I followed [this guide](https://www.pcsuggest.com/linux-bluetooth-setup-hcitool-bluez/) to get Bluetooth up and
running on my hardware. Your mileage may vary, especially if you're trying to use the Raspberry Pi built-in interface
(contributions to this guide very welcome!)

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
