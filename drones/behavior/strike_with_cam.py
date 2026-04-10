# Abandoned, wating for a better vision-based strike implementation.

# """Strike behavior helpers."""

# import asyncio
# import math
# import sys
# import threading
# from pathlib import Path
# from typing import List, Optional, Tuple

# from mavsdk import System
# from bridge import FGCBridge

# from utils import (
#     calculate_new_coordinates,
#     calculate_positions_distance,
#     calculate_relative_distance,
# )

# DETECT_YOLO_DIR = Path(__file__).resolve().parent.parent / "detect-yolo"
# if str(DETECT_YOLO_DIR) not in sys.path:
#     sys.path.append(str(DETECT_YOLO_DIR))

# from visdroneRUN_access import run_zmq_inference

# CRUISE_SPEED = 15.0
# SINK_SPEED = 5.0
# CLOSE_DISTANCE = 300.0
# EXTEND_DISTANCE = 100.0
# CHECK_INTERVAL = 0.5


# class VisDroneMonitor:
#     """Run VisDrone inference in a background thread and expose the latest detections."""

#     def __init__(self, linux_ip: str = "0.0.0.0", port: int = 5555):
#         self._linux_ip = linux_ip
#         self._port = port
#         self._lock = threading.Lock()
#         self._latest: List[dict] = []
#         self._frame_idx: Optional[int] = None
#         self._thread: Optional[threading.Thread] = None
#         self._stop_event = threading.Event()

#     def start(self) -> None:
#         if self._thread and self._thread.is_alive():
#             return
#         self._stop_event.clear()
#         self._thread = threading.Thread(target=self._run, name="visdrone-monitor", daemon=True)
#         self._thread.start()

#     def stop(self) -> None:
#         self._stop_event.set()
#         if self._thread:
#             self._thread.join(timeout=2.0)

#     def latest_snapshot(self) -> Tuple[Optional[int], List[dict]]:
#         with self._lock:
#             frame_idx = self._frame_idx
#             detections = list(self._latest)
#         return frame_idx, detections

#     def _run(self) -> None:
#         try:
#             run_zmq_inference(
#                 self._linux_ip,
#                 self._port,
#                 output_path=None,
#                 show_window=False,
#                 on_detections=self._update_detections,
#                 stop_event=self._stop_event,
#             )
#         except Exception as exc:  # noqa: BLE001
#             print(f"[VisDroneMonitor] detection loop failed: {exc}")

#     def _update_detections(self, detections: List[dict], frame_idx: int) -> None:
#         with self._lock:
#             self._latest = list(detections)
#             self._frame_idx = frame_idx


# async def starlink_strike_task(drone:System, bridge:FGCBridge, log_prefix, target,):
#     """
#     Hold current altitude until reaching the distance threshold, switch to 0 m inside it,
#     and when closer than CLOSE_DISTANCE push the target 100 m forward along the current heading at -10 m.
#     """
#     monitor = VisDroneMonitor()
#     monitor.start()

#     target_lat, target_lon = target[0], target[1]
#     pos = await drone.telemetry.position().__anext__()

#     hold_alt = pos.absolute_altitude_m
#     await drone.param.set_param_float("FW_AIRSPD_TRIM", CRUISE_SPEED)
#     await drone.param.set_param_float("FW_T_SINK_MAX", SINK_SPEED)
#     try:
#         async def goto_with_detections(lat: float, lon: float, alt: float, yaw: float) -> None:
#             await drone.action.goto_location(lat, lon, alt, yaw)
#             log_latest_detections(lat, lon, alt)

#         def log_latest_detections(lat: float, lon: float, alt: float) -> None:
#             frame_idx, detections = monitor.latest_snapshot()
#             goto_note = f"goto lat={lat:.6f}, lon={lon:.6f}, alt={alt:.1f}"
#             if frame_idx is None:
#                 bridge.send_log(f"{log_prefix} 检测尚未收到帧 | {goto_note}")
#                 return
#             if not detections:
#                 bridge.send_log(f"{log_prefix} 检测帧 {frame_idx}: 未发现目标 | {goto_note}")
#                 return

#             shown = min(3, len(detections))
#             summary_parts = []
#             for det in detections[:shown]:
#                 rel_x, rel_y = det.get("relative_center", (0.0, 0.0))
#                 summary_parts.append(
#                     f"{det.get('label', 'obj')} {det.get('confidence', 0.0):.2f} "
#                     f"norm=({rel_x:.2f},{rel_y:.2f})"
#                 )
#             if len(detections) > shown:
#                 summary_parts.append(f"... +{len(detections) - shown}")
#             summary = "; ".join(summary_parts)
#             bridge.send_log(f"{log_prefix} 检测帧 {frame_idx}: {summary} | {goto_note}")

#         await goto_with_detections(target_lat, target_lon, hold_alt, 0.0)
#         bridge.send_log(f"{log_prefix} 前往目标 lat={target_lat:.6f}, lon={target_lon:.6f}，保持高度 {hold_alt:.1f}m"    )

#         distance_threshold = max(hold_alt * 8.5, CLOSE_DISTANCE + 1.0)

#         while True:
#             pos = await drone.telemetry.position().__anext__()

#             horizontal = calculate_positions_distance(pos.latitude_deg, pos.longitude_deg, target_lat, target_lon)

#             if horizontal > distance_threshold:
#                 await goto_with_detections(target_lat, target_lon, hold_alt, 0.0)
#                 bridge.send_log(f"距目标 {horizontal:.1f}m，保持高度 {hold_alt:.1f}m")

#             elif horizontal > CLOSE_DISTANCE:
#                 await goto_with_detections(target_lat, target_lon, 0.0, 0.0)
#                 bridge.send_log(f"距目标 {horizontal:.1f}m，高度 {pos.absolute_altitude_m}m")

#             else:
#                 break
#             await asyncio.sleep(CHECK_INTERVAL)

#         bridge.send_log('进入近距，准备延伸目标点')
#         north_delta, east_delta = calculate_relative_distance(target_lat, target_lon, pos.latitude_deg, pos.longitude_deg)
#         forward_length = math.hypot(north_delta, east_delta)
#         if forward_length <= 1.0:
#             unit_north, unit_east = 1.0, 0.0
#         else:
#             unit_north = north_delta / forward_length
#             unit_east = east_delta / forward_length
#         cur_fwd_dist = horizontal
#         fwd_lat, fwd_lon = target_lat, target_lon

#         while True:
#             pos = await drone.telemetry.position().__anext__()
#             cur_fwd_dist = calculate_positions_distance(pos.latitude_deg, pos.longitude_deg, fwd_lat, fwd_lon)

#             if cur_fwd_dist <= CLOSE_DISTANCE:
#                 forward_north = unit_north * EXTEND_DISTANCE
#                 forward_east = unit_east * EXTEND_DISTANCE
#                 fwd_lat, fwd_lon = calculate_new_coordinates(fwd_lat, fwd_lon, forward_north, forward_east)
#                 cur_fwd_dist = calculate_positions_distance(pos.latitude_deg, pos.longitude_deg, fwd_lat, fwd_lon)
#                 bridge.send_log(f"{log_prefix} 延伸目标点至 lat={fwd_lat:.6f}, lon={fwd_lon:.6f}")

#             await goto_with_detections(fwd_lat, fwd_lon, 0, 0)
#             bridge.send_log(f"高度 {pos.absolute_altitude_m}m")
#             if pos.absolute_altitude_m <= 10:
#                 bridge.send_log(f"模拟打击完成！复飞中...")
#                 await goto_with_detections(fwd_lat, fwd_lon, 50, 0)
#                 break
#             await asyncio.sleep(CHECK_INTERVAL)
#     finally:
#         monitor.stop()


# def extract_starlink_target(payload):
#     """Extract a (lat, lon[, alt]) tuple from the standard starlink payload."""
#     if not isinstance(payload, dict):
#         return None
#     location = payload.get("location")
#     if not isinstance(location, (list, tuple)) or len(location) < 2:
#         return None

#     lat = location[0]
#     lon = location[1]
#     if lat is None or lon is None:
#         return None
    
#     return lat, lon, 0
