"""Quick test: controller -> engine -> mouse"""
import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import load_config
from src.engine import ModeEngine
from src.controller import _GamepadListener
from src.types import Button

config = load_config(os.path.join(os.path.dirname(__file__), 'config.yaml'))
listener = _GamepadListener(deadzone=config.global_.deadzone)
engine = ModeEngine(config, listener)

engine.start()
listener.start()

print('Mouse control active! Move sticks, press buttons...')
print('(Ctrl+C to stop)')
time.sleep(0.5)

last_key = None
try:
    while True:
        engine.tick()
        s = listener.state
        ls = s.left_stick
        rs = s.right_stick

        key = (round(ls.x, 1), round(ls.y, 1), round(rs.x, 1), round(rs.y, 1),
               tuple(sorted(b.name for b in Button if s.buttons[b].pressed)))
        if key != last_key:
            btns = [b.name for b in Button if s.buttons[b].pressed]
            print(f'LS({ls.x:+.2f},{ls.y:+.2f}) RS({rs.x:+.2f},{rs.y:+.2f}) '
                  f'LT={s.left_trigger.value:.1f} RT={s.right_trigger.value:.1f} '
                  f'BTN=[{",".join(btns) if btns else "-"}] mode={engine.current_mode}',
                  flush=True)
            last_key = key
        time.sleep(0.01)
except KeyboardInterrupt:
    pass
finally:
    engine.stop()
    listener.stop()
    print('Stopped')
