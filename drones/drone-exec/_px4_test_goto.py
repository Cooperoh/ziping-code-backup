#!/usr/bin/env python3
"""使用 MAVSDK 通过串口控制 PX4：起飞到 3 米，向前飞 10 米，再降落。"""

import asyncio
import math
import sys
from pathlib import Path

from mavsdk import System

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import (
    calculate_new_coordinates,
    calculate_positions_distance,
    resolve_goto_absolute_altitude,
)

SERIAL_ADDRESS = "serial:///dev/ttyACM0:57600"
TAKEOFF_ALT_M = 3.0
FORWARD_DISTANCE_M = 10.0
TARGET_REACHED_M = 1.0
ALT_TOLERANCE_M = 0.5
WAIT_TIMEOUT_S = 20.0
POLL_INTERVAL_S = 0.5


async def wait_until_armable(drone: System):
    print("等待飞控允许解锁...")
    async for health in drone.telemetry.health():
        if health.is_armable:
            print("飞控允许解锁")
            return


async def wait_until_position_ready(drone: System):
    print("等待全局位置估计...")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            print("全局位置估计正常")
            return


async def wait_until_armed(drone: System):
    print("等待 armed 状态确认...")
    async for armed in drone.telemetry.armed():
        if armed:
            print("无人机已解锁")
            return


async def wait_until_takeoff_altitude(drone: System, target_alt_m: float):
    print(f"等待爬升到 {target_alt_m:.1f}m 附近...")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + WAIT_TIMEOUT_S

    while True:
        position = await drone.telemetry.position().__anext__()
        relative_alt = getattr(position, "relative_altitude_m", None)
        if isinstance(relative_alt, (int, float)) and relative_alt >= target_alt_m - ALT_TOLERANCE_M:
            print(f"当前相对高度 {relative_alt:.1f}m，已达到起飞高度")
            return
        if loop.time() >= deadline:
            raise TimeoutError(f"等待达到起飞高度超时，当前高度={relative_alt}")
        await asyncio.sleep(POLL_INTERVAL_S)


async def wait_until_reached(drone: System, target_lat: float, target_lon: float):
    print(f"等待到达目标点（误差 {TARGET_REACHED_M:.1f}m 内）...")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + WAIT_TIMEOUT_S

    while True:
        position = await drone.telemetry.position().__anext__()
        distance_m = calculate_positions_distance(position.latitude_deg, position.longitude_deg, target_lat, target_lon,)
        if distance_m <= TARGET_REACHED_M:
            print(f"已到达目标点，当前位置距目标 {distance_m:.1f}m")
            return
        if loop.time() >= deadline:
            raise TimeoutError(f"等待到达目标点超时，当前距目标 {distance_m:.1f}m")
        await asyncio.sleep(POLL_INTERVAL_S)


async def wait_until_landed(drone: System):
    print("等待降落完成...")
    async for in_air in drone.telemetry.in_air():
        if not in_air:
            print("已落地")
            return


async def main():
    drone = System()

    print(f"正在连接飞控 ({SERIAL_ADDRESS}) ...")
    await drone.connect(system_address=SERIAL_ADDRESS)

    print("等待无人机连接...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("无人机已连接")
            break

    await wait_until_position_ready(drone)
    await wait_until_armable(drone)

    print(f"-- 设置起飞高度 {TAKEOFF_ALT_M:.1f}m")
    await drone.action.set_takeoff_altitude(TAKEOFF_ALT_M)

    print("-- 解锁 (Arming)")
    await drone.action.arm()
    await wait_until_armed(drone)

    print("-- 起飞 (Taking off)")
    await drone.action.takeoff()
    await wait_until_takeoff_altitude(drone, TAKEOFF_ALT_M)

    position = await drone.telemetry.position().__anext__()
    heading = await drone.telemetry.heading().__anext__()
    target_abs_alt = resolve_goto_absolute_altitude(position, TAKEOFF_ALT_M)

    yaw_deg = heading.heading_deg
    heading_rad = math.radians(yaw_deg)
    north_offset = FORWARD_DISTANCE_M * math.cos(heading_rad)
    east_offset = FORWARD_DISTANCE_M * math.sin(heading_rad)
    target_lat, target_lon = calculate_new_coordinates(position.latitude_deg, position.longitude_deg, north_offset, east_offset,)

    print(f"-- 向前飞 {FORWARD_DISTANCE_M:.1f}m "f"(heading={yaw_deg:.1f} deg, target=({target_lat}, {target_lon}))")
    await drone.action.goto_location(target_lat, target_lon, target_abs_alt, yaw_deg)
    await wait_until_reached(drone, target_lat, target_lon)

    print("-- 降落 (Landing)")
    await drone.action.land()
    await wait_until_landed(drone)

    await asyncio.sleep(2)
    print("-- 上锁 (Disarming)")
    try:
        await drone.action.disarm()
    except Exception as exc:
        print(f"disarm 跳过: {exc}")

    print("测试完成")


if __name__ == "__main__":
    asyncio.run(main())
