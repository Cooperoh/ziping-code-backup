import json
import os
import socket
import threading
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
import torch
import zmq
from ultralytics import YOLO
from ultralytics.utils.plotting import colors

SCRIPT_DIR = Path(__file__).resolve().parent
MODEL_PATH = SCRIPT_DIR / "yolov8n-visdrone.pt"

REPORT_HOST = "127.0.0.1"
REPORT_PORT = 3333  # 当前只做单机的


class _DetectionReportSocket:
    """Lazy TCP client that streams detection reports to a local listener."""

    def __init__(self, host: str, port: int):
        self._address = (host, port)
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._warned = False

    def send_report(self, payload: dict) -> None:
        message = json.dumps(payload) + "\n"
        data = message.encode("utf-8")
        with self._lock:
            sock = self._ensure_socket()
            if not sock:
                return
            try:
                sock.sendall(data)
                if self._warned:
                    print(f"[REPORT] 已连接 {self._address}, 继续推送检测")
                    self._warned = False
            except OSError:
                self._tear_down()

    def close(self) -> None:
        with self._lock:
            self._tear_down()

    def _ensure_socket(self) -> Optional[socket.socket]:
        if self._sock is not None:
            return self._sock
        try:
            sock = socket.create_connection(self._address, timeout=0.5)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            if not self._warned:
                print(f"[REPORT] 无法连接 {self._address}, 稍后重试")
                self._warned = True
            return None
        self._sock = sock
        self._warned = False
        return sock

    def _tear_down(self) -> None:
        if self._sock is None:
            return
        try:
            self._sock.close()
        except OSError:
            pass
        self._sock = None


_REPORT_CLIENT = _DetectionReportSocket(REPORT_HOST, REPORT_PORT)

_torch_load = torch.load
def _load_all(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _torch_load(*args, **kwargs)
torch.load = _load_all

model = YOLO(str(MODEL_PATH))

"""
Important! Dont delete this comment block.
0: pedestrian   1: people
2: bicycle      6: tricycle     7: awning-tricycle      9: motor
3: car          4: van          5: truck                8: bus
"""

target_ids = [3, 4, 5, 8]
target_show = [idx for idx, _ in model.names.items() if idx in target_ids]

# set model parameters
conf            = 0.7           # NMS confidence threshold, default 0.25, model.predict() high priority than model.overrides {"conf": 0.25, "save": is_cli}
iou             = 0.7           # NMS IoU threshold, default 0.70
agnostic_nms    = False         # NMS class-agnostic, default False
classes         = target_show   # filter by class, default None
max_det         = 100           # maximum number of detections per image, default 300
imgsz           = 960           # inference size, default 640


def draw_detections(frame_bgr, inference):
    """Draw YOLO detections on a BGR frame."""
    boxes = getattr(inference, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return frame_bgr

    rendered = frame_bgr.copy()
    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    classes_idx = boxes.cls.cpu().numpy().astype(int)

    text_scale = 0.5
    thickness = 1
    for (x1, y1, x2, y2), cls_id, conf in zip(xyxy, classes_idx, confs):
        cls_int = int(cls_id)
        color = colors(cls_int, bgr=True)
        label = model.names.get(cls_int, str(cls_int))
        caption = f"{label} {conf:.2f}"
        pt1 = (int(x1), int(y1))
        pt2 = (int(x2), int(y2))
        cv2.rectangle(rendered, pt1, pt2, color, 2)
        ((text_w, text_h), _) = cv2.getTextSize(caption, cv2.FONT_HERSHEY_SIMPLEX, text_scale, thickness)
        text_origin_y = max(pt1[1] - 4, text_h + 4)
        text_origin = (pt1[0] + 2, text_origin_y)
        bg_tl = (pt1[0], text_origin_y - text_h - 4)
        bg_br = (pt1[0] + text_w + 4, text_origin_y)
        cv2.rectangle(rendered, bg_tl, bg_br, color, -1)
        cv2.putText(rendered, caption, text_origin, cv2.FONT_HERSHEY_SIMPLEX, text_scale, (0, 0, 0), thickness, cv2.LINE_AA)

    return rendered


def collect_detections(inference, frame_shape):
    """Collect detection metadata (bbox, confidence, centers) for downstream use."""
    boxes = getattr(inference, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []

    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    classes_idx = boxes.cls.cpu().numpy().astype(int)

    height, width = frame_shape[:2]
    detections = []
    for (x1, y1, x2, y2), cls_id, conf in zip(xyxy, classes_idx, confs):
        center_x = (x1 + x2) / 2.0
        center_y = (y1 + y2) / 2.0
        detections.append(
            {
                "class_id": int(cls_id),
                "label": model.names.get(int(cls_id), str(int(cls_id))),
                "confidence": float(conf),
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                "center": [float(center_x), float(center_y)],
                "relative_center": [float(center_x / width), float(center_y / height)],
            }
        )

    return detections


def report_detections(detections, frame_idx=None):
    """Pretty-print detection info to stdout for quick monitoring."""
    if not detections:
        return

    prefix = f"Frame {frame_idx}" if frame_idx is not None else "Detections"
    print(f"{prefix}:")
    for det in detections:
        center_x, center_y = det["center"]
        rel_x, rel_y = det["relative_center"]
        bbox = det["bbox"]
        print(
            f"  - {det['label']} conf={det['confidence']:.2f} "
            f"center=({center_x:.1f}, {center_y:.1f}) norm=({rel_x:.3f}, {rel_y:.3f}) "
            f"bbox={bbox}"
        )
    payload = {
        "frame": frame_idx,
        "detections": detections,
    }
    _REPORT_CLIENT.send_report(payload)


def run_zmq_inference(
    linux_ip,
    port,
    output_path,
    show_window,
    on_detections: Optional[Callable[[list, int], None]] = None,
    stop_event=None,
    poll_timeout_ms: int = 100,
):
    """Run VisDrone model on frames received over a ZeroMQ JPEG stream."""
    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.SUB)
    sock.setsockopt(zmq.CONFLATE, 1)
    sock.setsockopt(zmq.RCVHWM, 1)
    sock.connect(f"tcp://{linux_ip}:{port}")
    sock.setsockopt(zmq.SUBSCRIBE, b"")

    writer = None
    window_name = "YOLOv8n-VisDrone ZMQ Stream"
    frame_idx = 0
    poller = zmq.Poller()
    poller.register(sock, zmq.POLLIN)
    try:
        while True:
            if stop_event is not None and hasattr(stop_event, "is_set") and stop_event.is_set():
                break

            events = dict(poller.poll(poll_timeout_ms))
            if sock not in events:
                continue

            jpg = sock.recv()
            frame_bgr = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
            if frame_bgr is None:
                continue

            if writer is None and output_path:
                height, width = frame_bgr.shape[:2]
                output = Path(output_path)
                output.parent.mkdir(parents=True, exist_ok=True)
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(str(output), fourcc, 30, (width, height))

            inference = model.predict(frame_bgr, verbose=False, classes=classes, conf=conf, iou=iou, agnostic_nms=agnostic_nms, imgsz=imgsz,)[0]
            detections = collect_detections(inference, frame_bgr.shape)
            report_detections(detections, frame_idx)
            if on_detections is not None:
                try:
                    on_detections(detections, frame_idx)
                except Exception as callback_exc:
                    print(f"[VisDrone] on_detections callback failed: {callback_exc}")
            rendered_frame = draw_detections(frame_bgr, inference)

            if show_window:
                cv2.imshow(window_name, rendered_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            if writer:
                writer.write(rendered_frame)
            frame_idx += 1
    finally:
        sock.close(0)
        if writer:
            writer.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":

    # Stream over ZeroMQ (JPEG frames)
    STREAM_IP = "0.0.0.0"
    STREAM_PORT = 5561
    run_zmq_inference(STREAM_IP, STREAM_PORT, output_path=None, show_window=True)
