"""Definitive controller test — run this to verify your gamepad works.

This tests ALL backends in priority order and shows exactly what data
each one produces. Move your sticks and press buttons while it runs!

Usage:
    python test_controller.py
"""
import sys, time, os

# Ensure we can import from src/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Init pygame in main thread ──
import pygame
pygame.init()
pygame.display.set_mode((1, 1), pygame.HIDDEN)

from src.controller import (
    _GamepadBackendSDL2, _GamepadBackendPygame, _GamepadBackendHID
)

print("=" * 60)
print("  CONTROLLER DIAGNOSTIC & TEST")
print("=" * 60)
print()

# ── Step 1: Check what's available ──
print("[1/3] Checking available backends...")
print()

# Try SDL2 GameController
print("  SDL2 GameController API: ", end="", flush=True)
try:
    from pygame._sdl2 import controller as sdl2_ctrl
    sdl2_ctrl.init()
    gc_count = sdl2_ctrl.get_count()
    print(f"YES — {gc_count} controller(s) detected")
    for i in range(gc_count):
        is_ctrl = sdl2_ctrl.is_controller(i)
        name = sdl2_ctrl.name_forindex(i)
        print(f"         [{i}] is_controller={is_ctrl} name=\"{name}\"")
except Exception as e:
    gc_count = 0
    print(f"NO — {e}")

print()

# Try SDL2 Joystick
print("  SDL2 Joystick API:    ", end="", flush=True)
try:
    pygame.joystick.init()
    joy_count = pygame.joystick.get_count()
    print(f"YES — {joy_count} joystick(s) detected")
    for i in range(joy_count):
        from pygame.joystick import Joystick
        j = Joystick(i)
        j.init()
        print(f"         [{i}] name=\"{j.get_name()}\" "
              f"axes={j.get_numaxes()} btns={j.get_numbuttons()} "
              f"hats={j.get_numhats()}")
        j.quit()
except Exception as e:
    joy_count = 0
    print(f"NO — {e}")

# Only try HID if both SDL2 backends found nothing
hid_available = False
if gc_count == 0 and joy_count == 0:
    print()
    print("  HID API:              ", end="", flush=True)
    try:
        import hid
        devices = hid.enumerate()
        gamepad_devices = [d for d in devices
                          if d.get('usage_page') == 0x01 and d.get('usage') in (0x04, 0x05, 0x06, 0x08)]
        print(f"YES — {len(gamepad_devices)} gamepad HID device(s)")
        for d in gamepad_devices:
            print(f"         {d.get('product_string', '?')} "
                  f"VID:{hex(d['vendor_id'])} PID:{hex(d['product_id'])}")
        hid_available = len(gamepad_devices) > 0
    except Exception as e:
        print(f"NO — {e}")

print()

if gc_count == 0 and joy_count == 0 and not hid_available:
    print("!" * 60)
    print("  NO CONTROLLER FOUND!")
    print("  Make sure your controller is:")
    print("  1. Turned ON (press the Xbox/PS button)")
    print("  2. Connected via Bluetooth or USB")
    print("  3. Not connected to another device (Xbox, phone, etc.)")
    print("!" * 60)
    pygame.quit()
    sys.exit(1)

# ── Step 2: Try each backend ──
print("[2/3] Testing backends (priority order)...")
print()

# Dummy listener for backend.create()
class DummyListener:
    _deadzone = 0.15

backend = None
backend_name = ""

# Try SDL2 GameController first
if gc_count > 0 and sdl2_ctrl.is_controller(0):
    print("  Trying SDL2 GameController backend...")
    be = _GamepadBackendSDL2.create(DummyListener())
    if be:
        backend = be
        backend_name = "SDL2 GameController"
        print(f"  -> Connected via {backend_name}: {be._ctrl.name}")
    else:
        print("  -> Failed to create SDL2 GameController backend")

# Try SDL2 Joystick if GC failed
if backend is None and joy_count > 0:
    print("  Trying SDL2 Joystick backend...")
    be = _GamepadBackendPygame.create(DummyListener())
    if be:
        backend = be
        backend_name = "SDL2 Joystick"
        print(f"  -> Connected via {backend_name}: {be._joy.get_name()}")
    else:
        print("  -> Failed to create SDL2 Joystick backend")

# Try HID as last resort
if backend is None and hid_available:
    print("  Trying HID backend...")
    be = _GamepadBackendHID.create(DummyListener())
    if be:
        backend = be
        backend_name = "HID"
        print(f"  -> Connected via {backend_name}")
    else:
        print("  -> Failed to create HID backend")

if backend is None:
    print()
    print("!" * 60)
    print("  Could not connect to controller via any backend!")
    print("  The controller is detected but can't be opened.")
    print("  This usually means another app has exclusive access.")
    print("  Solution: Restart your computer and try again.")
    print("!" * 60)
    sdl2_ctrl.quit()
    pygame.quit()
    sys.exit(1)

print()
print(f"  Using backend: {backend_name}")
print()

# ── Step 3: Poll for input ──
print("[3/3] Polling for input (30 seconds)")
print("=" * 60)
print("MOVE STICKS AND PRESS BUTTONS NOW!")
print("You should see values change below as you interact.")
print("Ctrl+C to stop early.")
print("=" * 60)
print()

start = time.monotonic()
last_state = None
poll_count = 0
data_count = 0
deadline = start + 30

try:
    while time.monotonic() < deadline:
        data = backend.read()
        poll_count += 1

        if data:
            data_count += 1
            # Build state tuple from data
            state = (
                round(data.get('lx', 0), 2),
                round(data.get('ly', 0), 2),
                round(data.get('rx', 0), 2),
                round(data.get('ry', 0), 2),
                round(data.get('lt', 0), 2),
                round(data.get('rt', 0), 2),
                tuple(sorted(k.name for k, v in data.get('buttons', {}).items() if v)),
            )

            if state != last_state:
                elapsed = time.monotonic() - start
                lx, ly, rx, ry, lt, rt, btns = state

                parts = []
                if abs(lx) > 0.01 or abs(ly) > 0.01:
                    parts.append(f"L-STICK({lx:+.2f}, {ly:+.2f})")
                if abs(rx) > 0.01 or abs(ry) > 0.01:
                    parts.append(f"R-STICK({rx:+.2f}, {ry:+.2f})")
                if lt > 0.05 or rt > 0.05:
                    parts.append(f"TRIG(L={lt:.2f}, R={rt:.2f})")
                if btns:
                    parts.append(f"BTN=[{','.join(btns)}]")

                if parts:
                    print(f"  [{elapsed:5.1f}s] {' | '.join(parts)}", flush=True)
                last_state = state

        time.sleep(0.005)  # ~200Hz polling

except KeyboardInterrupt:
    print("\nStopped by user.")

finally:
    elapsed = time.monotonic() - start
    print()
    print("=" * 60)
    print(f"  RESULTS (after {elapsed:.1f} seconds)")
    print(f"  Polls: {poll_count} | Data reads: {data_count}")
    print(f"  Backend: {backend_name}")
    if data_count == 0:
        print()
        print("  !!! ZERO data reads from controller !!!")
        print()
        print("  The controller is detected but not sending input data.")
        print("  This is a known issue with Bluetooth Xbox controllers")
        print("  and SDL 2.28.4 (bundled with pygame 2.6.1).")
        print()
        print("  TRY THESE FIXES (in order):")
        print("  1. Turn controller OFF then ON, then re-run this test")
        print("  2. Remove device from Windows Bluetooth settings,")
        print("     then re-pair (hold Xbox Pair button till logo flashes)")
        print("  3. Connect via USB cable (most reliable)")
        print("  4. Update SDL2: copy a newer SDL2.dll into pygame's folder")
        print("  5. Use Xbox Wireless Adapter instead of Bluetooth")
    elif last_state is None:
        print()
        print("  No input changes detected (controller idle).")
        print("  Did you move sticks / press buttons?")
    else:
        print()
        lx, ly, rx, ry, lt, rt, btns = last_state
        print(f"  Last state: LS({lx:+.2f},{ly:+.2f}) RS({rx:+.2f},{ry:+.2f}) "
              f"TRIG({lt:.2f},{rt:.2f}) BTN={btns}")
        print()
        print("  Controller is WORKING correctly!")

    if backend:
        backend.close()
    sdl2_ctrl.quit()
    pygame.joystick.quit()
    pygame.quit()

print()
print("Press Enter to exit...", end="")
input()
