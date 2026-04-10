import os

# Gazebo bindings ship protobufs generated for protoc<=3.19; force pure-Python runtime to stay compatible with newer protobuf wheels.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

import gz.transport13 as transport
from gz.msgs10.image_pb2 import Image
import numpy as np, cv2, time

TOPIC = "/world/default/model/rc_cessna_cam_0/link/base_link/sensor/front_camera/image"
node = transport.Node()
latest = {"frame": None}

def decode(pb):
    h, w = pb.height, pb.width
    if not h or not w or not pb.data: return None
    buf = np.frombuffer(pb.data, np.uint8)
    ch = buf.size // (h*w)
    if   ch == 3: return cv2.cvtColor(buf.reshape(h,w,3), cv2.COLOR_RGB2BGR)
    elif ch == 4: return cv2.cvtColor(buf.reshape(h,w,4), cv2.COLOR_RGBA2BGR)
    elif ch == 1: return buf.reshape(h,w,1)
    return None

def on_typed(pb):                   # 强类型：1 参数
    f = decode(pb)
    if f is not None: latest["frame"] = f

def on_raw(data, info):             # 原始：2 参数
    pb = Image(); pb.ParseFromString(data)
    on_typed(pb)

ok = False
try:
    ok = node.subscribe(TOPIC, on_typed, Image)      # 优先强类型
except Exception: pass
if not ok:
    try:
        ok = node.subscribe_raw(TOPIC, on_raw, "gz.msgs.Image")  # transport13 常见 3 参
    except TypeError:
        ok = node.subscribe_raw(TOPIC, on_raw, "gz.msgs.Image", transport.SubscribeOptions())

if not ok:
    raise RuntimeError("subscribe 失败；检查 GZ_IP/GZ_PARTITION/话题名")

print("订阅中:", TOPIC)
while True:
    if latest["frame"] is not None:
        cv2.imshow("Gazebo Camera", latest["frame"])
        if cv2.waitKey(1) == 27: break
    time.sleep(0.002)
cv2.destroyAllWindows()
