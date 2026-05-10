# Rubik's Connected — Home Assistant Integration

A custom integration for the [Rubik's Connected](https://www.rubiks.com/en-us/rubiks-connected) cube (and compatible GoCube devices) that exposes each face turn as a Home Assistant event and reports battery level as a sensor.

## Supported devices

| Device | Status |
|---|---|
| Rubik's Connected | ✅ Confirmed working |
| GoCube Edge | ✅ Same protocol, should work |
| GoCube (original) | ✅ Same protocol, should work |

All three use the Nordic UART Service (NUS) over Bluetooth LE with an identical binary protocol.

## Requirements

- Home Assistant **2024.1** or newer
- A Bluetooth adapter accessible to HA (built-in on Raspberry Pi 4/5, or a USB dongle)
- The **Bluetooth** integration enabled in HA (it is by default on HAOS)

## Installation

### HACS (recommended)

1. In HA, open **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/YOUR_USERNAME/ha-rubiks-connected` with category **Integration**
3. Find "Rubik's Connected" in HACS and click **Download**
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/rubiks_connected/` folder into your HA `/config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Power on the cube (give it a turn to wake it from sleep)
2. Go to **Settings → Integrations → + Add Integration**
3. Search for **Rubik's Connected**
4. If the cube is advertising, it will appear automatically — select it and confirm
5. If it doesn't appear, enter the Bluetooth address manually

To find the address without extra tools: **Settings → Integrations → Bluetooth** in HA lists all nearby BLE devices and their addresses.

## Entities

Each configured cube creates two entities:

| Entity | Type | Description |
|---|---|---|
| `sensor.rubiks_connected_battery` | Sensor | Battery level (%), updated every 5 minutes |
| `event.rubiks_connected_move` | Event | Fires on every face turn |

### Move event types

The move event fires one of 12 event types, named `<color>_<direction>`:

| Color | CW | CCW |
|---|---|---|
| White | `white_cw` | `white_ccw` |
| Yellow | `yellow_cw` | `yellow_ccw` |
| Red | `red_cw` | `red_ccw` |
| Orange | `orange_cw` | `orange_ccw` |
| Blue | `blue_cw` | `blue_ccw` |
| Green | `green_cw` | `green_ccw` |

The event also carries an `angle` attribute (the face's current rotation in degrees).

## Automation examples

### Toggle a light on white face turns

```yaml
trigger:
  - platform: state
    entity_id: event.rubiks_connected_move
    attribute: event_type
    to: white_cw
action:
  - service: light.toggle
    target:
      entity_id: light.desk_lamp
```

### Color ceiling lights to match the last turned face

```yaml
trigger:
  - platform: state
    entity_id: event.rubiks_connected_move
action:
  - service: light.turn_on
    target:
      entity_id: light.ceiling
    data:
      rgb_color: >
        {% set face = trigger.to_state.attributes.event_type.split('_')[0] %}
        {% set map = {
          'white':  [255, 255, 255],
          'red':    [255,   0,   0],
          'green':  [  0, 200,   0],
          'orange': [255, 100,   0],
          'blue':   [  0,   0, 255],
          'yellow': [255, 220,   0]
        } %}
        {{ map[face] }}
```

### Use a face turn as a scene selector

```yaml
trigger:
  - platform: state
    entity_id: event.rubiks_connected_move
action:
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.to_state.attributes.event_type == 'blue_cw' }}"
        sequence:
          - service: scene.turn_on
            target:
              entity_id: scene.movie_mode
      - conditions:
          - condition: template
            value_template: "{{ trigger.to_state.attributes.event_type == 'green_cw' }}"
        sequence:
          - service: scene.turn_on
            target:
              entity_id: scene.reading_mode
```

## Development

> **Normal users don't need any of this.** The `dev/` directory contains standalone Python scripts for exploring and verifying the BLE protocol — useful if you're hacking on the integration or adding support for a new device variant. They run on any Linux machine with Bluetooth and require `bleak`:

```bash
pip install bleak
```

| Script | Purpose |
|---|---|
| `scan.py` | Scan for nearby BLE devices |
| `capture.py` | Dump raw NUS notifications from the cube |
| `calibrate.py` | Guided calibration to verify the face→color map |
| `decode.py` | Real-time decoded move display |
| `parse_pcap.py` | Parse a BLE PCAP capture (requires `tshark`) |

## Protocol notes

The cube uses the Nordic UART Service:
- Service UUID: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- Notify characteristic: `6e400003-...`
- Write characteristic: `6e400002-...`

Packets follow the format `2a [type] [sub] [payload...] [checksum] 0d 0a` where the checksum is the sum of all preceding bytes masked to 8 bits.

Move packets are 8 bytes; a single-byte `0x32` written to the write characteristic requests a battery report.

## License

MIT
