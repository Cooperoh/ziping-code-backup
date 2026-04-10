# pip install pyzmq opencv-python numpy
import os

# Gazebo Python bindings still target the pure-Python protobuf runtime; make sure the import uses the compatible implementation.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

import argparse, time, cv2, numpy as np, zmq, subprocess
import gz.transport13 as transport
from gz.msgs10.image_pb2 import Image

p = argparse.ArgumentParser()
p.add_argument("--topic", default=os.getenv("GZ_CAM_TOPIC",""), help="gz image topic")
p.add_argument("--port", type=int, default=5561)
p.add_argument("--scale", type=float, default=1.0)
p.add_argument("--quality", type=int, default=80)
args = p.parse_args()

ctx = zmq.Context.instance()
sock = ctx.socket(zmq.PUB)
sock.setsockopt(zmq.SNDHWM, 1)
sock.setsockopt(zmq.CONFLATE,1)
sock.bind(f"tcp://0.0.0.0:{args.port}")

node = transport.Node()
last_ts = time.time(); frames = 0

def decode(pb):
    h, w = pb.height, pb.width
    if not h or not w or not pb.data: return None
    arr = np.frombuffer(pb.data, np.uint8)
    ch = arr.size // (h*w)
    if ch == 3: img = cv2.cvtColor(arr.reshape(h,w,3), cv2.COLOR_RGB2BGR)
    elif ch == 4: img = cv2.cvtColor(arr.reshape(h,w,4), cv2.COLOR_RGBA2BGR)
    elif ch == 1: img = arr.reshape(h,w,1)
    else: return None
    if args.scale != 1.0:
        img = cv2.resize(img, (int(w*args.scale), int(h*args.scale)), interpolation=cv2.INTER_AREA)
    return img

def on_typed(pb):
    global frames, last_ts
    img = decode(pb)
    if img is None: return
    ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), args.quality])
    if ok: sock.send(enc.tobytes(), copy=False)
    frames += 1
    now = time.time()
    if now - last_ts >= 2.0:
        print(f"[PUB] ~{frames/(now-last_ts):.1f} fps  port={args.port}")
        last_ts = now; frames = 0

def on_raw(data, info):
    pb = Image(); pb.ParseFromString(data); on_typed(pb)

topic = args.topic
if not topic:
    try:
        out = subprocess.check_output(['bash','-lc',"gz topic -l | grep '/image' | head -n1"], text=True)
        topic = out.strip()
    except Exception:
        topic = ""

if not topic:
    raise SystemExit("未找到 image 话题；先用 `gz topic -l | grep image` 再用 --topic 指定。")

ok = False
try: ok = node.subscribe(topic, on_typed, Image)
except Exception: pass
if not ok:
    try: ok = node.subscribe_raw(topic, on_raw, "gz.msgs.Image")
    except TypeError:
        ok = node.subscribe_raw(topic, on_raw, "gz.msgs.Image", transport.SubscribeOptions())
if not ok: raise SystemExit(f"订阅失败：{topic}")

print(f"[PUB] listening topic: {topic}")
print(f"[PUB] bind tcp://0.0.0.0:{args.port}")
while True: time.sleep(1)
