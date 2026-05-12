"""手柄诊断 — hidapi 后端。"""
import hid
import struct
from src.controller import find_controllers, XboxReportParser

print("=== hidapi 手柄诊断 ===\n")

print("1. 查找手柄设备...")
ctrls = find_controllers()
if ctrls:
    for c in ctrls:
        print(f"   {c}")
else:
    print("   未找到游戏手柄 (usage_page=1, usage in 4,5,6)")
    print("\n   列出所有HID设备供排查:")
    for d in hid.enumerate():
        name = d.get('product_string', '(no name)')
        up = d.get('usage_page', 0)
        u = d.get('usage', 0)
        if name != '(no name)':
            print(f"   {name}: usage_page={up}, usage={u}")

print()

# 尝试打开并读取
print("2. 尝试打开设备并读取...")
device = None
for d in hid.enumerate():
    up = d.get('usage_page', 0)
    u = d.get('usage', 0)
    if up == 0x01 and u in (0x04, 0x05, 0x06, 0x08):
        try:
            device = hid.device()
            device.open_path(d['path'])
            device.set_nonblocking(True)
            print(f"   已打开: {d.get('product_string', 'unknown')}")
            break
        except Exception as e:
            print(f"   打开失败: {e}")

if device:
    import time
    print("   等待读取(3秒)...移动摇杆或按按钮")
    parser = XboxReportParser()
    start = time.monotonic()
    while time.monotonic() - start < 3:
        data = device.read(64, timeout_ms=100)
        if data and len(data) >= 14:
            p = parser.parse(bytes(data))
            if p:
                print(f"   LX:{p['lx']:+.3f} LY:{p['ly']:+.3f} RX:{p['rx']:+.3f} RY:{p['ry']:+.3f} LT:{p['lt']:.2f} RT:{p['rt']:.2f}")
                pressed = [b.name for b, v in p['buttons'].items() if v]
                if pressed:
                    print(f"   按钮: {', '.join(pressed)}")
                if p['dpad'] != (0, 0):
                    print(f"   十字键: {p['dpad']}")
    device.close()
    print("   测试完成")
else:
    print("   无法打开任何手柄设备")
