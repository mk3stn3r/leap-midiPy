# leap_midi — Leap Motion v1 → MIDI  (WebSocket edition)

Reads hand tracking data from **leapd's WebSocket API** (`ws://localhost:6437`)
and sends MIDI notes + CC to any connected USB MIDI device.
No Leap SDK Python bindings required.

## Dependencies

```bash
sudo apt install libasound2-dev   # needed to build rtmidi's ALSA backend
pip install websocket-client python-rtmidi
```

## Running

```bash
# Terminal 1 — keep leapd running
sudo leapd

# Terminal 2
python3 leap_midi.py --list-ports   # see USB MIDI ports
python3 leap_midi.py --port 0       # start (Ctrl+C stops cleanly)
python3 leap_midi.py --port 0 --mapping my.json
```

The script reconnects automatically if leapd restarts.

## mapping.json reference

| Key | Type | Description |
|---|---|---|
| `midi_channel` | 0–15 | MIDI channel (0 = ch.1) |
| `velocity_fixed` | int or null | Fixed velocity, or null = dynamic from hand openness |
| `ws_url` | string | leapd WebSocket URL (default v6.json) |
| `left_hand.axis` | string | See axis table below |
| `left_hand.note_min/max` | 0–127 | MIDI note range for the axis |
| `left_hand.cc_send` | bool | Also send a CC alongside the note |
| `left_hand.cc_number` | 0–127 | CC number |
| `left_hand.trigger_mode` | gate/retrigger | gate = hold note while hand present |
| `right_hand.*` | — | Same options as left_hand |
| `gestures.*` | object | type + optional direction + note + velocity |
| `gesture_note_duration` | float | Seconds to hold gesture notes |

## Axis options

| Axis | What it tracks |
|---|---|
| `palm_y` | Hand height (default — lower hand = lower note) |
| `palm_x` | Left/right position |
| `palm_z` | Depth (forward/back) |
| `sphere_radius` | How open/closed the hand is |
| `pinch` | Pinch strength thumb↔index |
| `grab` | Overall grab / fist strength |
| `roll` | Palm roll around wrist axis |
| `pitch` | Hand tilt front-to-back |
| `yaw` | Hand yaw left/right swivel |

## Gesture types (from leapd)

`swipe`, `circle`, `keyTap`, `screenTap`  
Add `"direction": "left"` or `"right"` to filter swipe direction.
