#!/usr/bin/env python3
"""
leap_midi.py  —  Leap Motion Controller v1  →  MIDI Notes
==========================================================
Uses leapd's built-in WebSocket API (ws://localhost:6437/v6.json).
NO Leap SDK files required — leapd alone is enough.

Dependencies
------------
  pip install websocket-client python-rtmidi

  On Linux Mint you may need ALSA headers first:
    sudo apt install libasound2-dev

Usage
-----
  sudo leapd &                            # start the Leap daemon (separate terminal)
  python3 leap_midi.py --list-ports       # list available MIDI output ports
  python3 leap_midi.py --port 0           # run (Ctrl+C to stop cleanly)
  python3 leap_midi.py --port 0 --mapping minitaur.json
"""

import sys, os, json, math, time, argparse, threading, signal

try:
    import websocket
except ImportError:
    sys.exit("[FATAL] websocket-client not found.\n  Run: pip install websocket-client")

try:
    import rtmidi
except ImportError:
    sys.exit("[FATAL] python-rtmidi not found.\n  Run: pip install python-rtmidi")


# ── default mapping ───────────────────────────────────────────────────────────
DEFAULT_MAPPING = {
    "_info": "leap_midi mapping — edit freely, restart script to reload.",
    "midi_channel": 0,
    "velocity_fixed": None,
    "ws_url": "ws://localhost:6437/v6.json",
    "left_hand": {
        "axis": "palm_y", "note_min": 48, "note_max": 72,
        "cc_send": False, "cc_number": 1, "cc_axis": "grab",
        "trigger_mode": "gate"
    },
    "right_hand": {
        "axis": "palm_y", "note_min": 60, "note_max": 84,
        "cc_send": True,  "cc_number": 74, "cc_axis": "roll",
        "trigger_mode": "gate"
    },
    "gestures": {
        "swipe_left":            {"type": "swipe",     "direction": "left",             "note": 36, "velocity": 100},
        "swipe_right":           {"type": "swipe",     "direction": "right",            "note": 38, "velocity": 100},
        "swipe_up":              {"type": "swipe",     "direction": "up",               "note": 40, "velocity": 100},
        "swipe_down":            {"type": "swipe",     "direction": "down",             "note": 41, "velocity": 100},
        "swipe_toward":          {"type": "swipe",     "direction": "toward",           "note": 42, "velocity": 100},
        "swipe_away":            {"type": "swipe",     "direction": "away",             "note": 43, "velocity": 100},
        "circle_cw":             {"type": "circle",    "direction": "clockwise",        "note": 44, "velocity": 100},
        "circle_ccw":            {"type": "circle",    "direction": "counterclockwise", "note": 45, "velocity": 100},
        "key_tap":               {"type": "keyTap",                                     "note": 46, "velocity": 110},
        "screen_tap_right_0":    {"type": "screenTap", "hand": "right", "finger": 0,   "note": 48, "velocity": 100},
        "screen_tap_right_1":    {"type": "screenTap", "hand": "right", "finger": 1,   "note": 50, "velocity": 100},
        "screen_tap_right_2":    {"type": "screenTap", "hand": "right", "finger": 2,   "note": 52, "velocity": 100},
        "screen_tap_right_3":    {"type": "screenTap", "hand": "right", "finger": 3,   "note": 53, "velocity": 100},
        "screen_tap_right_4":    {"type": "screenTap", "hand": "right", "finger": 4,   "note": 55, "velocity": 100},
        "screen_tap_left_0":     {"type": "screenTap", "hand": "left",  "finger": 0,   "note": 36, "velocity": 100},
        "screen_tap_left_1":     {"type": "screenTap", "hand": "left",  "finger": 1,   "note": 38, "velocity": 100},
        "screen_tap_left_2":     {"type": "screenTap", "hand": "left",  "finger": 2,   "note": 40, "velocity": 100},
        "screen_tap_left_3":     {"type": "screenTap", "hand": "left",  "finger": 3,   "note": 41, "velocity": 100},
        "screen_tap_left_4":     {"type": "screenTap", "hand": "left",  "finger": 4,   "note": 43, "velocity": 100},
        "key_tap_right_0":       {"type": "keyTap",    "hand": "right", "finger": 0,   "note": 60, "velocity": 110},
        "key_tap_right_1":       {"type": "keyTap",    "hand": "right", "finger": 1,   "note": 62, "velocity": 110},
        "key_tap_right_2":       {"type": "keyTap",    "hand": "right", "finger": 2,   "note": 64, "velocity": 110},
        "key_tap_right_3":       {"type": "keyTap",    "hand": "right", "finger": 3,   "note": 65, "velocity": 110},
        "key_tap_right_4":       {"type": "keyTap",    "hand": "right", "finger": 4,   "note": 67, "velocity": 110},
        "key_tap_left_0":        {"type": "keyTap",    "hand": "left",  "finger": 0,   "note": 48, "velocity": 110},
        "key_tap_left_1":        {"type": "keyTap",    "hand": "left",  "finger": 1,   "note": 50, "velocity": 110},
        "key_tap_left_2":        {"type": "keyTap",    "hand": "left",  "finger": 2,   "note": 52, "velocity": 110},
        "key_tap_left_3":        {"type": "keyTap",    "hand": "left",  "finger": 3,   "note": 53, "velocity": 110},
        "key_tap_left_4":        {"type": "keyTap",    "hand": "left",  "finger": 4,   "note": 55, "velocity": 110}
    },
    "gesture_note_duration": 0.12,

    # circle CC mode: when set, circle CW/CCW send CC increments instead of notes
    # set to null to disable and use note triggers instead
    "circle_cc": None
}


# ── helpers ───────────────────────────────────────────────────────────────────

def load_mapping(path):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(DEFAULT_MAPPING, f, indent=2)
        print(f"[INFO] Created default mapping: {path}")
    with open(path) as f:
        m = json.load(f)
    print(f"[INFO] Loaded mapping: {path}")
    return m


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def normalise_palm(hand, ibox):
    pos    = hand.get("palmPosition", [0, 200, 0])
    center = ibox.get("center", [0, 200, 0])
    size   = ibox.get("size",   [300, 300, 300])
    nx = clamp((pos[0] - center[0]) / size[0] + 0.5, 0.0, 1.0)
    ny = clamp((pos[1] - center[1]) / size[1] + 0.5, 0.0, 1.0)
    nz = clamp(1.0 - ((pos[2] - center[2]) / size[2] + 0.5), 0.0, 1.0)
    return nx, ny, nz


def hand_axis(hand, ibox, axis):
    nx, ny, nz = normalise_palm(hand, ibox)
    if axis == "palm_x":       return nx
    if axis == "palm_y":       return ny
    if axis == "palm_z":       return nz
    if axis == "sphere_radius":
        r = hand.get("sphereRadius", 80.0)
        return clamp((r - 40) / 80.0, 0.0, 1.0)
    normal    = hand.get("palmNormal", [0, -1, 0])
    direction = hand.get("direction",  [0, 0, -1])
    if axis == "roll":
        return clamp((math.atan2(normal[0], -normal[1]) + math.pi) / (2 * math.pi), 0.0, 1.0)
    if axis == "pitch":
        return clamp((math.atan2(direction[1], -direction[2]) + math.pi / 2) / math.pi, 0.0, 1.0)
    if axis == "yaw":
        return clamp((math.atan2(direction[0], -direction[2]) + math.pi) / (2 * math.pi), 0.0, 1.0)
    if axis == "pinch":  return clamp(hand.get("pinchStrength", 0.0), 0.0, 1.0)
    if axis == "grab":   return clamp(hand.get("grabStrength",  0.0), 0.0, 1.0)
    return ny


def note_from_value(v, note_min, note_max):
    return int(round(note_min + v * (note_max - note_min)))


def velocity_from_hand(hand, fixed):
    if fixed is not None:
        return int(clamp(fixed, 1, 127))
    r = hand.get("sphereRadius", 80.0)
    return int(clamp((r - 40) / 80.0 * 127, 1, 127))


# ── MIDI ──────────────────────────────────────────────────────────────────────

class MidiOut:
    NOTE_ON  = 0x90
    NOTE_OFF = 0x80
    CC       = 0xB0

    def __init__(self, port_index):
        self._out = rtmidi.MidiOut()
        ports = self._out.get_ports()
        if not ports:
            raise RuntimeError(
                "No MIDI output ports found.\n"
                "  Make sure your USB MIDI device is connected.\n"
                "  Run  aconnect -l  to verify ALSA sees it."
            )
        if port_index >= len(ports):
            raise RuntimeError(f"Port {port_index} out of range. Available: {list(enumerate(ports))}")
        self._out.open_port(port_index)
        print(f"[MIDI] Output → {ports[port_index]}")

    def note_on(self, ch, note, vel):
        self._out.send_message([self.NOTE_ON  | ch, note & 0x7F, vel & 0x7F])

    def note_off(self, ch, note):
        self._out.send_message([self.NOTE_OFF | ch, note & 0x7F, 0])

    def cc(self, ch, num, val):
        self._out.send_message([self.CC | ch, num & 0x7F, int(clamp(val, 0, 127)) & 0x7F])

    def all_notes_off(self, ch):
        self._out.send_message([self.CC | ch, 123, 0])

    def close(self):
        del self._out


# ── per-hand state ────────────────────────────────────────────────────────────

class HandState:
    def __init__(self, cfg, midi, channel, fixed_vel):
        self.cfg       = cfg
        self.midi      = midi
        self.ch        = channel
        self.fixed_vel = fixed_vel
        self.active    = None

    def update(self, hand, ibox):
        val  = hand_axis(hand, ibox, self.cfg["axis"])
        note = note_from_value(val, self.cfg["note_min"], self.cfg["note_max"])
        vel  = velocity_from_hand(hand, self.fixed_vel)

        if self.cfg.get("cc_send"):
            cc_axis = self.cfg.get("cc_axis", self.cfg["axis"])
            cc_val  = int(hand_axis(hand, ibox, cc_axis) * 127)
            self.midi.cc(self.ch, self.cfg["cc_number"], cc_val)

        if self.active != note:
            if self.active is not None:
                self.midi.note_off(self.ch, self.active)
            self.midi.note_on(self.ch, note, vel)
            self.active = note

    def release(self):
        if self.active is not None:
            self.midi.note_off(self.ch, self.active)
            self.active = None


# ── gesture handler ───────────────────────────────────────────────────────────

# finger index within a hand: 0=thumb 1=index 2=middle 3=ring 4=pinky
FINGER_NAMES = ["thumb", "index", "middle", "ring", "pinky"]

def _swipe_direction(g):
    """Return dominant direction string for a swipe gesture."""
    d = g.get("direction", [1, 0, 0])
    ax, ay, az = abs(d[0]), abs(d[1]), abs(d[2])
    if ax >= ay and ax >= az:
        return "right" if d[0] > 0 else "left"
    if ay >= ax and ay >= az:
        return "up"    if d[1] > 0 else "down"
    return "away" if d[2] < 0 else "toward"


def _circle_direction(g, pointables):
    """Return 'clockwise' or 'counterclockwise' for a circle gesture."""
    # leapd gives us the pointable (finger) id; normal vector of circle plane
    # points toward viewer for CCW, away for CW (right-hand rule)
    normal = g.get("normal", [0, 0, -1])
    # If z-component of normal points toward viewer (negative z in Leap coords = toward screen)
    # that indicates CCW from user's perspective; positive z = CW
    if normal[2] <= 0:
        return "clockwise"
    return "counterclockwise"


def _finger_index_for_gesture(g, pointables, hands):
    """
    Return (hand_type, finger_index) for a keyTap or screenTap gesture.
    pointables: list of pointable dicts from the frame
    hands: list of hand dicts from the frame
    """
    pid = g.get("pointableIds", [None])[0] if g.get("pointableIds") else None
    if pid is None:
        return None, None

    # find the pointable
    p = next((x for x in pointables if isinstance(x, dict) and x.get("id") == pid), None)
    if p is None:
        return None, None

    hand_id     = p.get("handId")
    finger_idx  = p.get("type", None)   # leapd v6: 0=thumb..4=pinky on pointable

    hand = next((h for h in hands if isinstance(h, dict) and h.get("id") == hand_id), None)
    hand_type = hand.get("type", "right") if hand else "right"

    return hand_type, finger_idx


class GestureHandler:
    def __init__(self, mapping, midi, channel):
        self.gcfg      = mapping.get("gestures", {})
        self.midi      = midi
        self.ch        = channel
        self.duration  = mapping.get("gesture_note_duration", 0.12)
        self.circle_cc = mapping.get("circle_cc", None)  # {"cc_number":74, "step":5}
        self._fired    = set()
        # running CC value for circle mode
        self._circle_cc_val = 64

    def handle(self, gestures, pointables, hands):
        for g in gestures:
            if not isinstance(g, dict): continue
            gid   = g.get("id")
            gtype = g.get("type", "")
            state = g.get("state", "")

            if state == "stop":
                self._fired.discard(gid)
                continue
            if gid in self._fired:
                continue
            if state not in ("start", "update"):
                continue
            # for circle in CC mode we want update events too
            if state == "update" and not (gtype == "circle" and self.circle_cc):
                continue

            # ── circle CC mode ────────────────────────────────────────────────
            if gtype == "circle" and self.circle_cc:
                if state == "start":
                    self._fired.add(gid)
                cdir  = _circle_direction(g, pointables)
                step  = self.circle_cc.get("step", 5)
                ccnum = self.circle_cc.get("cc_number", 74)
                delta = step if cdir == "clockwise" else -step
                self._circle_cc_val = int(clamp(self._circle_cc_val + delta, 0, 127))
                self.midi.cc(self.ch, ccnum, self._circle_cc_val)
                print(f"  ↳ circle {cdir}  CC{ccnum}={self._circle_cc_val}")
                continue

            # ── resolve gesture variant ───────────────────────────────────────
            resolved = {}
            if gtype == "swipe":
                resolved["direction"] = _swipe_direction(g)
            elif gtype == "circle":
                resolved["direction"] = _circle_direction(g, pointables)
            elif gtype in ("keyTap", "screenTap"):
                h_type, f_idx = _finger_index_for_gesture(g, pointables, hands)
                resolved["hand"]   = h_type
                resolved["finger"] = f_idx

            # ── find matching mapping entry ───────────────────────────────────
            match = None
            for key, cfg in self.gcfg.items():
                if cfg.get("type") != gtype:
                    continue
                # direction filter (swipe + circle)
                if "direction" in cfg and cfg["direction"] != resolved.get("direction"):
                    continue
                # hand filter (keyTap / screenTap)
                if "hand" in cfg and cfg["hand"] != resolved.get("hand"):
                    continue
                # finger filter
                if "finger" in cfg and cfg["finger"] != resolved.get("finger"):
                    continue
                match = cfg
                break

            if match and state == "start":
                self._fired.add(gid)
                note = match["note"]
                vel  = match.get("velocity", 100)
                ch, dur, midi = self.ch, self.duration, self.midi
                label = f"{gtype} {resolved}"
                print(f"  ↳ {label}  note {note}")
                def _play(n=note, v=vel, c=ch, d=dur):
                    midi.note_on(c, n, v)
                    time.sleep(d)
                    midi.note_off(c, n)
                threading.Thread(target=_play, daemon=True).start()


# ── main WebSocket loop ───────────────────────────────────────────────────────

class LeapMidi:
    def __init__(self, mapping, midi):
        self.mapping  = mapping
        self.midi     = midi
        self.ch       = mapping.get("midi_channel", 0)
        fv            = mapping.get("velocity_fixed", None)

        self.left  = HandState(mapping["left_hand"],  midi, self.ch, fv)
        self.right = HandState(mapping["right_hand"], midi, self.ch, fv)
        self.ghandler = GestureHandler(mapping, midi, self.ch)

        self._prev_hand_ids  = set()
        self._prev_types     = {}
        self._stop           = threading.Event()
        self._ws             = None

    def _on_open(self, ws):
        print("[WS]  Connected to leapd")
        ws.send(json.dumps({"enableGestures": True}))
        ws.send(json.dumps({"background": True}))

    def _on_message(self, ws, raw):
        try:
            frame = json.loads(raw)
        except Exception:
            return

        if "event" in frame:
            print(f"[Leap] {frame['event'].get('type','')}")
            return

        hands       = frame.get("hands", [])
        pointables  = frame.get("pointables", [])
        ibox        = frame.get("interactionBox", {})
        gestures    = frame.get("gestures", [])

        current_ids = {h["id"] for h in hands}

        left_hand = right_hand = None
        for h in hands:
            if not isinstance(h, dict): continue
            if h.get("type") == "left":  left_hand  = h
            if h.get("type") == "right": right_hand = h

        if left_hand:  self.left.update(left_hand,  ibox)
        if right_hand: self.right.update(right_hand, ibox)

        gone = self._prev_hand_ids - current_ids
        for gid in gone:
            side = self._prev_types.get(gid, "")
            if side == "left":  self.left.release()
            if side == "right": self.right.release()

        self._prev_types    = {h["id"]: h.get("type","") for h in hands}
        self._prev_hand_ids = current_ids

        if gestures:
            self.ghandler.handle(gestures, pointables, hands)

    def _on_error(self, ws, error):
        print(f"[WS]  Error: {error}")

    def _on_close(self, ws, code, msg):
        print(f"[WS]  Closed (code={code})")
        self.left.release()
        self.right.release()
        self.midi.all_notes_off(self.ch)

    def run(self):
        url = self.mapping.get("ws_url", "ws://localhost:6437/v6.json")
        print(f"[WS]  Connecting to {url}")
        while not self._stop.is_set():
            self._ws = websocket.WebSocketApp(
                url,
                on_open    = self._on_open,
                on_message = self._on_message,
                on_error   = self._on_error,
                on_close   = self._on_close,
            )
            self._ws.run_forever(ping_interval=20, ping_timeout=10)
            if not self._stop.is_set():
                print("[WS]  Reconnecting in 2 s…")
                time.sleep(2)

    def stop(self):
        self._stop.set()
        if self._ws:
            self._ws.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

def list_ports():
    out   = rtmidi.MidiOut()
    ports = out.get_ports()
    if not ports:
        print("No MIDI output ports found.")
    else:
        print("Available MIDI output ports:")
        for i, p in enumerate(ports):
            print(f"  {i}: {p}")
    del out


def main():
    ap = argparse.ArgumentParser(
        description="Leap Motion (leapd WebSocket) → MIDI — Linux Mint 21.3"
    )
    ap.add_argument("--list-ports", action="store_true")
    ap.add_argument("--port",    type=int, default=0)
    ap.add_argument("--mapping", default="mapping.json")
    args = ap.parse_args()

    if args.list_ports:
        list_ports()
        return

    mapping = load_mapping(args.mapping)

    try:
        midi = MidiOut(args.port)
    except RuntimeError as e:
        sys.exit(f"[FATAL] {e}")

    engine     = LeapMidi(mapping, midi)
    stop_event = threading.Event()

    def _shutdown(sig, frame):
        print("\n[leap_midi] Shutting down…")
        engine.stop()
        stop_event.set()

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    ws_thread = threading.Thread(target=engine.run, daemon=True)
    ws_thread.start()

    print("[leap_midi] Running — press Ctrl+C to stop\n")
    stop_event.wait()
    ws_thread.join(timeout=3)

    midi.all_notes_off(mapping.get("midi_channel", 0))
    midi.close()
    print("[leap_midi] Done.")


if __name__ == "__main__":
    main()
