"""Telemetry streaming helpers."""

import asyncio
import math

from .constants import CHECK_INT


async def push_basic_telemetry(drone, bridge, tag, idx):
    """Continuously forward basic telemetry to the bridge."""
    while True:
        pos = await drone.telemetry.position().__anext__()
        hea = await drone.telemetry.heading().__anext__()
        vel = await drone.telemetry.velocity_ned().__anext__()
        speed = math.hypot(vel.north_m_s, vel.east_m_s)
        bridge.send_telemetry(
            id=idx,
            tag=tag,
            lat=pos.latitude_deg,
            lon=pos.longitude_deg,
            speed=speed,
            heading=round(hea.heading_deg),
        )
        await asyncio.sleep(CHECK_INT)
