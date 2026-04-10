"""Leader drone behaviors."""

import asyncio
import math
import random

from utils import (
    calculate_new_coordinates,
    calculate_positions_distance,
    calculate_relative_distance,
    resolve_goto_absolute_altitude,
)

from .constants import ALT_TKOF, CHECK_INT, CRUISE_SPEED, LEG_DIST, REACH_R, TRAIL_DIST


async def leader_patrol_task(lead, bridge, form_ref):
    """Broadcast current leader telemetry for formation followers."""
    while True:
        try:
            pos = await lead.telemetry.position().__anext__()
            hea = await lead.telemetry.heading().__anext__()
            vel = await lead.telemetry.velocity_ned().__anext__()
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(CHECK_INT)
            continue

        speed = math.hypot(vel.north_m_s, vel.east_m_s)
        bridge.send_to_peers(
            {
                "type": "lead_broadcast",
                "lat": pos.latitude_deg,
                "lon": pos.longitude_deg,
                "heading": round(hea.heading_deg),
                "speed": speed,
                "form_type": int(form_ref.get("type", 1)),
                "spacing": float(form_ref.get("spacing", TRAIL_DIST)),
                "group": form_ref.get("group", "all"),
                "leader_id": form_ref.get("leader_id"),
                "targets": list(form_ref.get("targets", [])),
            }
        )
        await asyncio.sleep(CHECK_INT)


async def leader_patrol_task_keep_fly_demo(lead, bridge, form_ref):
    """Fly patrol legs while broadcasting formation targets to peers."""
    await lead.action.set_current_speed(CRUISE_SPEED)

    pos = await lead.telemetry.position().__anext__()
    cur_lat, cur_lon = pos.latitude_deg, pos.longitude_deg
    hea = await lead.telemetry.heading().__anext__()
    heading = hea.heading_deg
    while True:
        rad = math.radians(heading)
        north_off = LEG_DIST * math.cos(rad)
        east_off = LEG_DIST * math.sin(rad)
        tgt_lat, tgt_lon = calculate_new_coordinates(cur_lat, cur_lon, north_off, east_off)
        cmd_pos = await lead.telemetry.position().__anext__()
        cmd_lat, cmd_lon = cmd_pos.latitude_deg, cmd_pos.longitude_deg
        target_abs_alt = resolve_goto_absolute_altitude(cmd_pos, ALT_TKOF)
        north_delta, east_delta = calculate_relative_distance(tgt_lat, tgt_lon, cmd_lat, cmd_lon)
        if abs(north_delta) < 1e-6 and abs(east_delta) < 1e-6:
            yaw_deg = heading
        else:
            yaw_deg = (math.degrees(math.atan2(east_delta, north_delta)) + 360.0) % 360.0
        await lead.action.goto_location(tgt_lat, tgt_lon, target_abs_alt, yaw_deg)
        bridge.send_telemetry(
            id=form_ref.get("leader_id"),
            goto_lat=tgt_lat,
            goto_lon=tgt_lon,
        )

        while True:
            pos = await lead.telemetry.position().__anext__()
            hea = await lead.telemetry.heading().__anext__()
            vel = await lead.telemetry.velocity_ned().__anext__()
            speed = math.hypot(vel.north_m_s, vel.east_m_s)

            # only broadcast to peers; GUI telemetry由外部 push_basic_telemetry 统一负责
            bridge.send_to_peers(
                {
                    "type": "lead_broadcast",
                    "lat": pos.latitude_deg,
                    "lon": pos.longitude_deg,
                    "heading": round(hea.heading_deg),
                    "speed": speed,
                    "form_type": int(form_ref.get("type", 1)),
                    "spacing": float(form_ref.get("spacing", TRAIL_DIST)),
                    "group": form_ref.get("group", "all"),
                    "leader_id": form_ref.get("leader_id"),
                    "targets": list(form_ref.get("targets", [])),
                }
            )
            bridge.send_telemetry(
                id=form_ref.get("leader_id"),
                goto_lat=tgt_lat,
                goto_lon=tgt_lon,
            )

            if calculate_positions_distance(pos.latitude_deg, pos.longitude_deg, tgt_lat, tgt_lon) <= REACH_R * 2:
                break
            await asyncio.sleep(CHECK_INT)

        await asyncio.sleep(0.5)
        cur_lat, cur_lon = tgt_lat, tgt_lon
        heading = (heading + random.uniform(-90.0, 90.0)) % 360.0
