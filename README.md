# hass-divoom
## Divoom Integration for Home Assistant

### Credits
First of, the whole communication with the Divoom device (focused on my Pixoo for now) is based on gathering information from multiple sources,
that already reverse engineered an older or different Divoom device. Therefore credit goes to the following owners and git repos (you are the heroes here):

https://github.com/RomRider/node-divoom-timebox-evo/ (especially for the [protocol documentation](https://github.com/RomRider/node-divoom-timebox-evo/blob/master/PROTOCOL.md))  
https://github.com/mumpitzstuff/fhem-Divoom  
https://github.com/ScR4tCh/timebox/  
https://bitbucket.org/pjhardy/homeassistant-timebox/src/master/

### Documentation
Further documentation besides the steps below and possibly a HACS integration may follow. For now I'm happy that it works! :D

#### Install the custom component

* Download the repository. If you know git, a clone is fine. If not,
  just download https://github.com/d03n3rfr1tz3/hass-divoom/archive/main.zip
  to get the most recent code in a zip file.
* Copy the content of that zip file into `custom_components\divoom` in your Home Assistant
  configuration directory.
* Create a directory named `pixelart` in your Home Assistant configuration directory,
  for images that you may want to display on your device.

#### Enable the custom component

This custom component adds a new platform to the Notifications
component. It can be enabled by adding this to your `configuration.yaml`:

```yaml
notify:
  - name: NOTIFIER_NAME
    platform: divoom
    mac: "DIVOOM_DEVICE_MAC_ADDRESS"
    device_type: "DIVOOM_DEVICE_TYPE"
    media_directory: "pixelart"
```

* name (Optional): The name for the notifier.
* mac (Required): The Bluetooth MAC address for the Divoom device.
* device_type: The concrete type of your Divoom device. Currently only `pixoo` is supported.
* media_directory (Required): A directory, relative to the configuration dir, containing image
  files in GIF format. The component will use these to display static or animated images on the device.

#### Usage

This custom component acts as a notify platform. This means that the
Service Data requires a message parameter, even though we're not using
it. Leave the message parameter blank, and specify mode and other
information in the data parameter of the Service Data payload.

### Basic display modes

```json
{
  "message": "",
  "data": {
    "mode": "MODE"
  }
}
```

`MODE` on all currently supported Divoom devices can be one of:

* `clock`: Display the built-in clock channel. You can specify the style in the `clock` parameter.
  This mode also accepts the boolean-like parameters `weather`, `temp` and `calendar` for activating the corresponding features.
  It's also possible to specify the `color` of the clock.
  * `clock` parameter accepts a number between 0 and 9. The actual supported clock styles depend on your device.\
    0 = Fullscreen, 1 = Rainbow, 2 = Boxed, 3 = Analog square,\
    4 = Fullscreen negative, 5 = Analog round, 6 = Widescreen
* `light`: Display the built-in light channel.
  It's also possible to specify the `brightness` and `color` of the clock.
* `effects`: Display the built-in effects channel. With the parameter `number` you can
  specify the concrete effect. Look into your phone app and count them.
* `visualization`: Display the built-in visualization channel. With the parameter `number` you can
  specify the concrete effect. Look into your phone app and count them.
* `scoreboard`: Display the built-in scoreboard channel. With the parameters `player1` and `player2`
  you can specify the displayed score.
* `image`: Display an animated or static image. The parameter `file` specifes the image file relative
  to the configured media_directory, that will be displayed.
* `brightness`: Sets the brightness using the `brightness` or `value` parameter.
* `datetime`: Sets the date and time using the `value` parameter in the typical ISO datetime format.
* `weather`: Sets the weather. Set the temperature using the `value` parameter and the weather type using the `weather` parameter.\
  1 = clear, 3 = cloudy sky, 5 = thunderstorm, 6 = rain, 8 = snow, 9 = fog
* `off`: Turn the display off.

`MODE` on timebox, ditoo and similar Divoom devices additionally support:

* `playstate`: Sets the play/pause state using the `value` parameter.
* `radio`: Shows the radio using the `value` parameter. Additionally the `frequency` can be set.
* `volume`: Sets the volume using the `volume` or `value` parameter.

#### Bluetooth interface

This component automatically connects to your Divoom device based on the configured MAC address. The only thing you typically have to prepare, is pairing it once to your Home Assistant device (for example your raspberry pi). Depending on your setup, that might be an easy or quite complicated task. After the pairing is done, this component can connect to your Divoom device anytime it's needed, even after restarting your Home Assistant. Newer versions of Home Assistant very likely already have Bluetooth enabled and configured somehow. Older versions needed more manual steps to make it work.

You can get the MAC address using your Phones Bluetooth settings or from your Divoom app. When trying to pair the devices, you will probably use tools, that are also capable of scanning. Therefore you can also get the MAC address that way.

##### Bluetooth preparation

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

### Examples
Examples for Pixoo: https://github.com/d03n3rfr1tz3/hass-divoom/blob/master/devices/pixoo.txt \
Examples for Pixoo Max: https://github.com/d03n3rfr1tz3/hass-divoom/blob/master/devices/pixoomax.txt \
Examples for Pixoo 64: https://github.com/d03n3rfr1tz3/hass-divoom/blob/master/devices/pixoo64.txt \
Examples for Timebox / Timebox Evo: https://github.com/d03n3rfr1tz3/hass-divoom/blob/master/devices/timebox.txt \
Examples for Ditoo: https://github.com/d03n3rfr1tz3/hass-divoom/blob/master/devices/ditoo.txt
