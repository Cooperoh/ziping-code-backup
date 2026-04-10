from ultralytics import YOLO
import torch
import cv2
import numpy as np
from pathlib import Path
from ultralytics import YOLO
from ultralytics.utils.plotting import colors
import zmq

# Load the YOLOv11 model
# model = YOLO("yolov11n-visdrone.pt")

SCRIPT_DIR = Path(__file__).resolve().parent
MODEL_PATH = SCRIPT_DIR / "yolov11n-visdrone.pt"

_torch_load = torch.load
def _load_all(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _torch_load(*args, **kwargs)
torch.load = _load_all

model = YOLO(str(MODEL_PATH))

# Export the model to RKNN format
# 'name' can be one of rk3588, rk3576, rk3566, rk3568, rk3562, rv1103, rv1106, rv1103b, rv1106b, rk2118
model.export(format="rknn", name="rk3588")  # creates '/yolo11n_rknn_model'