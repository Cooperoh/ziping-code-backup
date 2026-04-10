"""Follower drone behaviors."""

import asyncio
import math

from utils import (
    calculate_new_coordinates,
    calculate_positions_distance,
    calculate_relative_distance,
    get_offset,
    normalize_targets,
    resolve_goto_absolute_altitude,
    safe_float,
)

from .constants import (
    ALT_TKOF,
    CHECK_INT,
    FOLLOW_ERR_DEADBAND,
    FOLLOW_SPEED_BASE,
    FOLLOW_SPEED_GAIN,
    FOLLOW_SPEED_MAX,
    FOLLOW_SPEED_MIN,
    LOOKAHEAD_MAX,
    LOOKAHEAD_MIN,
    LOOKAHEAD_SPACING_GAIN,
    LOOKAHEAD_SPEED_TIME,
    TRAIL_DIST,
)


async def follower_task(
    fol,
    bridge,
    slot_index,
    drone_id,
    form_ref,
):
    """Track formation targets and adjust speed to maintain spacing."""
    last_lead = None
    current_slot = max(1, int(slot_index))

    async def _rx_loop():
        nonlocal last_lead, current_slot
        while True:
            msg = await bridge.next_peer()
            if not isinstance(msg, dict) or msg.get("type") != "lead_broadcast":
                continue

            # 只响应自己主机的广播
            my_leader_id = form_ref.get("leader_id")
            if my_leader_id is None or msg.get("leader_id") != my_leader_id:
                continue

            # 确认本机在编队成员列表中
            targets = normalize_targets(msg.get("targets"))
            if targets and drone_id not in targets:
                continue

            followers = [tid for tid in targets if tid != my_leader_id] if targets else []
            if followers and drone_id in followers:
                current_slot = followers.index(drone_id) + 1

            last_lead = msg

    rx_task = asyncio.create_task(_rx_loop())
    try:
        while True:
            if not last_lead:
                await asyncio.sleep(0.05)
                continue

            form_type = int(last_lead.get("form_type", form_ref.get("type", 1)))
            spacing = float(last_lead.get("spacing", form_ref.get("spacing", TRAIL_DIST)))
            heading = float(last_lead.get("heading", 0.0))
            lead_lat = float(last_lead.get("lat"))
            lead_lon = float(last_lead.get("lon"))
            lead_speed = safe_float(last_lead.get("speed"), FOLLOW_SPEED_BASE)
            lead_speed = max(FOLLOW_SPEED_MIN, min(FOLLOW_SPEED_MAX, lead_speed))

            heading_rad = math.radians(heading)
            offset_north, offset_east = get_offset(current_slot, form_type, spacing)
            tgt_north = offset_north * math.cos(heading_rad) - offset_east * math.sin(heading_rad)
            tgt_east = offset_north * math.sin(heading_rad) + offset_east * math.cos(heading_rad)

            tgt_lat, tgt_lon = calculate_new_coordinates(lead_lat, lead_lon, tgt_north, tgt_east)

            # ensure commanded waypoint stays far enough ahead of the follower before pushing further
            cur_pos = await fol.telemetry.position().__anext__()
            cur_lat, cur_lon = cur_pos.latitude_deg, cur_pos.longitude_deg
            target_abs_alt = resolve_goto_absolute_altitude(cur_pos, ALT_TKOF)
            delta = spacing * LOOKAHEAD_SPACING_GAIN + lead_speed * LOOKAHEAD_SPEED_TIME
            delta = max(LOOKAHEAD_MIN, min(LOOKAHEAD_MAX, delta))
            fwd_north = tgt_north + delta * math.cos(heading_rad)
            fwd_east = tgt_east + delta * math.sin(heading_rad)
            fwd_lat, fwd_lon = calculate_new_coordinates(lead_lat, lead_lon, fwd_north, fwd_east)

            cur_fwd_dist = calculate_positions_distance(cur_lat, cur_lon, fwd_lat, fwd_lon)
            if cur_fwd_dist < delta * 0.6: 
                delta = min(LOOKAHEAD_MAX, delta + max(2.0, spacing * 0.5))
                fwd_north = tgt_north + delta * math.cos(heading_rad)
                fwd_east = tgt_east + delta * math.sin(heading_rad)
                fwd_lat, fwd_lon = calculate_new_coordinates(lead_lat, lead_lon, fwd_north, fwd_east)

            yaw_north, yaw_east = calculate_relative_distance(fwd_lat, fwd_lon, cur_lat, cur_lon)
            if abs(yaw_north) < 1.0 and abs(yaw_east) < 1.0:
                goto_yaw = heading
            else:
                goto_yaw = (math.degrees(math.atan2(yaw_east, yaw_north)) + 360.0) % 360.0
            await fol.action.goto_location(fwd_lat, fwd_lon, target_abs_alt, goto_yaw)

            err_north, err_east = calculate_relative_distance(cur_lat, cur_lon, tgt_lat, tgt_lon)
            fwd_err = err_north * math.cos(heading_rad) + err_east * math.sin(heading_rad)
            if abs(fwd_err) < FOLLOW_ERR_DEADBAND:
                tgt_spd = lead_speed
            else:
                tgt_spd = lead_speed - FOLLOW_SPEED_GAIN * fwd_err
            tgt_spd = max(FOLLOW_SPEED_MIN, min(FOLLOW_SPEED_MAX, tgt_spd))

            # Report only the commanded goto waypoint coordinates for ground station.
            bridge.send_telemetry(id=drone_id, goto_lat=fwd_lat, goto_lon=fwd_lon)

            await fol.action.set_current_speed(round(tgt_spd, 1))

            await asyncio.sleep(CHECK_INT)
    finally:
        rx_task.cancel()
        try:
            await rx_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await fol.action.set_current_speed(FOLLOW_SPEED_BASE)
        except Exception:
            pass
