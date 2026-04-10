"""Takeoff related helpers."""

import asyncio
from mavsdk import System

from .constants import (
    ALT_CHECK_INTERVAL,
    ALT_TKOF,
    ALT_TOLERANCE,
    ALT_WAIT_TIMEOUT,
    ARM_DELAY,
    CRUISE_SPEED,
    TAKEOFF_DELAY,
)


def _extract_altitude(position):
    """Best-effort altitude extraction from telemetry position samples."""
    for attr in ("relative_altitude_m", "altitude_m", "absolute_altitude_m"):
        value = getattr(position, attr, None)
        if isinstance(value, (int, float)):
            return float(value)
    return None


async def _wait_until_altitude(drone, target):
    """Wait for aircraft to climb near target altitude before proceeding."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + ALT_WAIT_TIMEOUT
    latest = None
    while True:
        try:
            position = await drone.telemetry.position().__anext__()
        except StopAsyncIteration:
            # Generator ended unexpectedly; abort wait.
            break
        latest = _extract_altitude(position)
        if latest is not None and latest >= target - ALT_TOLERANCE:
            break
        if loop.time() >= deadline:
            if latest is not None:
                print(f"takeoff altitude wait timed out at {latest:.1f}m (target {target:.1f}m)")
            else:
                print(f"takeoff altitude wait timed out without altitude data (target {target:.1f}m)")
            break
        await asyncio.sleep(ALT_CHECK_INTERVAL)

async def set_speed(drone:System):
    """Best-effort speed setup using the generic action API."""
    try:
        await drone.action.set_current_speed(CRUISE_SPEED)
        return True
    except Exception as exc:
        print(f"set_current_speed({CRUISE_SPEED}) failed: {exc}")
        return False

async def arm_and_takeoff(drone:System):
    """Arm the vehicle, climb to the standard takeoff altitude, then enter hold."""
    await drone.action.arm()
    await asyncio.sleep(ARM_DELAY)
    try:
        await drone.action.set_takeoff_altitude(ALT_TKOF)
    except Exception as exc:
        print(f"set_takeoff_altitude({ALT_TKOF}) failed: {exc}")
    await drone.action.takeoff()
    await asyncio.sleep(TAKEOFF_DELAY)
    await _wait_until_altitude(drone, ALT_TKOF)
    try:
        await drone.action.hold()
    except Exception as exc:
        # Some stacks may reject the hold command before achieving takeoff altitude; log and continue.
        print(f"hold command after takeoff failed: {exc}")
    if await set_speed(drone):
        print(f"drone speed set: current={CRUISE_SPEED}m/s")
