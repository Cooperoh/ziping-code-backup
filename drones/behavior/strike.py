"""Strike behavior helpers."""

import asyncio
import json
import math

from mavsdk import System
from mavsdk.offboard import OffboardError, AttitudeRate
from bridge import FGCBridge

from utils import calculate_positions_distance, resolve_goto_absolute_altitude

CRUISE_SPEED = 20.0
CLOSE_DISTANCE = 300.0
CHECK_INTERVAL = 0.5
REPORT_HOST = "127.0.0.1"
REPORT_PORT = 3333  # 当前只做单机的
REPORT_QUEUE_MAX = 100
_LATEST_VISION_FEED = None
VISION_MIN_CONFIDENCE = 0.30




def _safe_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class VisionFeed:
    """Keep only the latest raw detection payload and expose the best target."""

    def __init__(self, *, min_confidence=VISION_MIN_CONFIDENCE, label_whitelist=None):
        self._min_conf = float(min_confidence)
        self._labels = {lbl.strip().lower() for lbl in label_whitelist} if label_whitelist else None
        self._latest_payload = None
        self._latest_timestamp = None

    def update(self, payload):
        self._latest_payload = payload
        try:
            loop = asyncio.get_running_loop()
            self._latest_timestamp = loop.time()
        except RuntimeError:
            self._latest_timestamp = None
        return self._select_detection(payload)

    def latest(self):
        payload = self._latest_payload
        if not payload:
            return None, None, None
        return payload, self._select_detection(payload), self._latest_timestamp

    def _select_detection(self, payload):
        detections = payload.get("detections") or []
        best_det = None
        best_conf = self._min_conf
        for det in detections:
            conf = _safe_float(det.get("confidence"))
            if conf is None or conf < best_conf:
                continue
            label = str(det.get("label", "")).strip().lower()
            if self._labels and label not in self._labels:
                continue
            rel = det.get("relative_center")
            if not isinstance(rel, (list, tuple)) or len(rel) < 2:
                continue
            best_det = det
            best_conf = conf
        return best_det


class DetectionReportServer:
    """Accept JSON detection reports over TCP and expose them via an asyncio queue."""

    def __init__(self, host, port, max_queue=REPORT_QUEUE_MAX):
        self._host = host
        self._port = port
        self._server = None
        self._queue = asyncio.Queue(maxsize=max_queue)

    async def start(self):
        if self._server is not None:
            return
        self._server = await asyncio.start_server(self._handle_client, self._host, self._port)

    async def stop(self):
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def next_report(self):
        return await self._queue.get()

    async def _handle_client(self, reader, writer):
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                line = raw.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                self._enqueue(payload)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    def _enqueue(self, payload):
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass


def latest_detection_summary():
    """Get a brief summary of the latest detection from the global vision feed."""
    feed = _LATEST_VISION_FEED
    if feed is None:
        return None, None
    
    payload, detection, _ = feed.latest()
    if payload is None:
        return None, None
    
    frame_idx = payload.get("frame")
    if detection:
        label = detection.get("label", "object")
        confidence = _safe_float(detection.get("confidence"), 0.0) or 0.0
        rel = detection.get("relative_center") or (0.5, 0.5)
        rel_x = _safe_float(rel[0], 0.5) or 0.5
        rel_y = _safe_float(rel[1], 0.5) or 0.5
        summary = f"frame={frame_idx} {label} conf={confidence:.2f} rel=({rel_x:.3f},{rel_y:.3f})"
        return [frame_idx, label, confidence, rel_x, rel_y], summary
    
    detections = payload.get("detections") or []
    if detections:
        summary = f"frame={frame_idx} 有 {len(detections)} 个检测但未通过筛选" 
        return None, summary # 检测列表里有目标，但没通过筛选的内容
    
    summary = f"frame={frame_idx} 无检测" if frame_idx is not None else "无检测"

    return None, summary


def log_latest_detection(log_prefix="", bridge=None):
    """Log the latest detection summary to the bridge and return the result."""
    result, summary = latest_detection_summary()
    if summary is None:
        message = f"{log_prefix} 视觉数据尚未就绪".strip()
    else:
        message = f"{log_prefix} 最新检测 {summary}".strip()
    if bridge is not None:
        try:
            # bridge.send_log(message)
            pass
        except Exception:
            pass
    return result


_DETECTION_SERVER = None
_DETECTION_LOCK = None


async def detection_results(bridge:FGCBridge, log_prefix, vision_feed=None):
    global _DETECTION_SERVER, _DETECTION_LOCK
    if _DETECTION_SERVER is None:
        if _DETECTION_LOCK is None:
            _DETECTION_LOCK = asyncio.Lock()
        async with _DETECTION_LOCK:
            if _DETECTION_SERVER is None:
                _DETECTION_SERVER = DetectionReportServer(REPORT_HOST, REPORT_PORT)
                await _DETECTION_SERVER.start() # 防止多协程抢同一个端口，报错 Address already in use，单机其实没啥用
    server = _DETECTION_SERVER
    while True:
        payload = await server.next_report()
        if not isinstance(payload, dict):
            continue
        selected_det = None
        if vision_feed is not None:
            try:
                selected_det = vision_feed.update(payload)
            except Exception as exc:  # noqa: BLE001
                try:
                    bridge.send_log(f"{log_prefix} detection tracker error: {exc}")
                except Exception:  # noqa: BLE001
                    pass
        try:
            frame_idx = payload.get("frame")
            detections = payload.get("detections") or []
            header = "[VisDrone]"
            if frame_idx is not None:
                header += f" frame {frame_idx}"
            if not detections:
                summary = f"{header} no detections"
            else:
                parts = []
                for det in detections[:3]:
                    label = det.get("label", "object")
                    confidence = det.get("confidence", 0.0)
                    try:
                        score = float(confidence)
                    except (TypeError, ValueError):
                        score = 0.0
                    rel = det.get("relative_center")
                    if isinstance(rel, (list, tuple)) and len(rel) >= 2:
                        rel_x, rel_y = rel[0], rel[1]
                    else:
                        rel_x, rel_y = 0.0, 0.0
                    parts.append(f"{label} {score:.2f} ({rel_x:.2f},{rel_y:.2f})")
                if len(detections) > 3:
                    parts.append(f"+{len(detections) - 3} more")
                summary = f"{header} {'; '.join(parts)}"
                if selected_det:
                    rel = selected_det.get("relative_center", (0.5, 0.5))
                    rel_x = _safe_float(rel[0], 0.5) or 0.5
                    rel_y = _safe_float(rel[1], 0.5) or 0.5
                    label = selected_det.get("label", "object")
                    confidence = _safe_float(selected_det.get("confidence"), 0.0) or 0.0
                    summary += (
                        f" | target locked {label} conf={confidence:.2f} rel=({rel_x:.2f},{rel_y:.2f})"
                    )
        except Exception as exc:  
            try:
                bridge.send_log(f"{log_prefix} detection report error: {exc}")
            except Exception:  
                pass
            continue
        try:
            # bridge.send_log(f"{log_prefix} {summary}")
            pass
        except Exception: 
            pass




async def starlink_strike_task(drone:System, bridge:FGCBridge, log_prefix, target):
    """
    Hold current altitude until reaching the distance threshold, switch to 0 m inside it,
    and when closer than CLOSE_DISTANCE push the target 100 m forward along the current heading at -10 m.
    """
    global _LATEST_VISION_FEED
    vision_feed = VisionFeed()
    _LATEST_VISION_FEED = vision_feed
    detection_task = asyncio.create_task(detection_results(bridge, log_prefix, vision_feed))
    try:
        target_lat, target_lon = target[0], target[1]
        pos = await drone.telemetry.position().__anext__()

        hold_alt = pos.absolute_altitude_m
        try:
            await drone.action.set_current_speed(CRUISE_SPEED)
        except Exception as exc:
            try:
                bridge.send_log(f"{log_prefix} set_current_speed failed, use autopilot default speed: {exc}")
            except Exception:
                pass
        await drone.action.goto_location(target_lat, target_lon, hold_alt, 0.0)
        bridge.send_log(f"{log_prefix} 前往目标 lat={target_lat:.6f}, lon={target_lon:.6f}，保持高度 {hold_alt:.1f}m")

        distance_threshold = max(hold_alt * 10, CLOSE_DISTANCE + 1.0)

        while True:
            pos = await drone.telemetry.position().__anext__()

            horizontal = calculate_positions_distance(pos.latitude_deg, pos.longitude_deg, target_lat, target_lon)

            if horizontal > distance_threshold:
                await drone.action.goto_location(target_lat, target_lon, hold_alt, 0.0)
                if horizontal//1%5==0: bridge.send_log(f"距目标 {horizontal:.1f}m，保持高度 {hold_alt:.1f}m")
            else:
                break
            await asyncio.sleep(CHECK_INTERVAL)
            
            message = log_latest_detection(log_prefix, bridge)
            if message is not None and message[0]%10==0: print(f"检测到目标 {message[1]}，但距离打击点太远")

        bridge.send_log(f"距目标 {horizontal:.1f}m，准备打击")

        # TODO 如果此时没有检测到目标，那么无人机应该继续朝着目标点飞行，直到抵达某个值而放弃打击，而不是直接进入打击逻辑，否则会报错
        # ---------------------【【【重要↑】】】-----------------------------

        # ================================打击逻辑=========================================
        offboard_started = False
        log_second = 0
        prev_attitude = None
        ANGLE_JUMP_THRESHOLD = 50.0
        while True:
            pos = await drone.telemetry.position().__anext__()
            att = await drone.telemetry.attitude_euler().__anext__()

            if prev_attitude is not None:
                delta_roll = abs(att.roll_deg - prev_attitude.roll_deg)
                delta_pitch = abs(att.pitch_deg - prev_attitude.pitch_deg)
                delta_yaw = abs(att.yaw_deg - prev_attitude.yaw_deg)
                if max(delta_roll, delta_pitch, delta_yaw) >= ANGLE_JUMP_THRESHOLD:
                    warning = "检测到碰撞！！！程序已退出"
                    try:
                        bridge.send_log(f"{log_prefix} {warning}")
                    except Exception:
                        pass
                    if offboard_started:
                        try:
                            await drone.offboard.stop()
                        except OffboardError:
                            pass
                    break
            prev_attitude = att

            message = log_latest_detection(log_prefix, bridge)
            if message is None and pos.absolute_altitude_m <= 5:
                bridge.send_log(f"目标丢失！高度过低！复飞中...")
                go_around_alt = resolve_goto_absolute_altitude(pos, 50.0)
                await drone.action.goto_location(target_lat, target_lon, go_around_alt, 0)
                break

            if message is not None:
                rel_x = _safe_float(message[3], 0.5) or 0.5
                rel_y = _safe_float(message[4], 0.5) or 0.5
            
            # 如果此时没检测到目标，那么就会因为 rel_x/rel_y 未定义而触发异常，直接进入 finally
            
            # 正x 轴：从左到右递增，y 轴：从上到下递增，原点 (0, 0)：位于图像左上角
            x = rel_x - 0.5   
            y = rel_y - 0.5   
            
            ATT_ROLL_MAX = 30
            ATT_PITCH_MAX = 30
            THRUST_BASE = 0.5
            roll_deg  = ATT_ROLL_MAX * x * 2
            pitch_deg = ATT_PITCH_MAX * y * 2 if y > 0 else ATT_PITCH_MAX * y * 2 * 1.2
            thrust_value = THRUST_BASE + (-y * 2 * 0.4)  # 上移增加推力，下移减少推力


            attitude_rate_setpoint = AttitudeRate(roll_deg_s=roll_deg, pitch_deg_s=-pitch_deg, yaw_deg_s=0.0, thrust_value=thrust_value)

            try:
                if not offboard_started:
                    for _ in range(5):
                        await drone.offboard.set_attitude_rate(attitude_rate_setpoint)
                        await asyncio.sleep(0.05)
                    await drone.offboard.start()
                    offboard_started = True
                    bridge.send_log("视觉引导控制已进入 Offboard AttitudeRate 模式")

                await drone.offboard.set_attitude_rate(attitude_rate_setpoint)
                if log_second % 10 == 0:
                    bridge.send_log(f"视觉引导中，目标相对位置 x={x:.3f}, y={y:.3f}，{roll_deg:.1f}, {-pitch_deg:.1f}，当前{att.roll_deg:.1f}, {att.pitch_deg:.1f}")
                log_second += 1
            except OffboardError as exc:
                bridge.send_log(f"Offboard 控制失败：{exc}")
                break

            await asyncio.sleep(0.1)
            
    finally:
        bridge.send_log(f"任务已结束...")

        detection_task.cancel()
        await asyncio.gather(detection_task, return_exceptions=True)


def extract_starlink_target(payload):
    """Extract a (lat, lon[, alt]) tuple from the standard starlink payload."""
    if not isinstance(payload, dict):
        return None
    location = payload.get("location")
    if not isinstance(location, (list, tuple)) or len(location) < 2:
        return None

    lat = location[0]
    lon = location[1]
    if lat is None or lon is None:
        return None
    
    return lat, lon, 0
