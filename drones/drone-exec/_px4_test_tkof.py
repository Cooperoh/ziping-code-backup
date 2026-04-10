#!/usr/bin/env python3
"""使用 MAVSDK 通过串口控制 PX4 无人机起飞和降落"""

import asyncio
from mavsdk import System


async def main():
    drone = System()

    # 通过 ttyACM0 串口连接飞控
    print("正在连接飞控 (serial:///dev/ttyACM0:57600) ...")
    await drone.connect(system_address="serial:///dev/ttyACM0:57600")

    # 等待连接建立
    print("等待无人机连接...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("无人机已连接")
            break

    # 等待 GPS 定位和全局位置估计可用
    print("等待全局位置估计...")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            print("全局位置估计正常")
            break

    # 检查当前是否可以解锁
    print("等待飞控允许解锁...")
    async for health in drone.telemetry.health():
        if health.is_armable:
            print("飞控允许解锁")
            break

    # 设置起飞高度和返航高度
    print("-- 设置起飞高度 2.5m")
    await drone.action.set_takeoff_altitude(2.5)
    await drone.action.set_return_to_launch_altitude(10.0)

    # 解锁并起飞
    print("-- 解锁 (Arming)")
    await drone.action.arm()

    print("-- 起飞 (Taking off)")
    await drone.action.takeoff()

    # 悬停 10 秒
    print("-- 悬停 10 秒...")
    await asyncio.sleep(10)

    # 降落
    print("-- 降落 (Landing)")
    await drone.action.land()

    # 等待降落完成（检测是否已落地）
    print("等待降落完成...")
    async for in_air in drone.telemetry.in_air():
        if not in_air:
            print("已落地")
            break

    # 等一会确保完全停稳再上锁
    await asyncio.sleep(2)

    # 上锁
    print("-- 上锁 (Disarming)")
    await drone.action.disarm()

    print("测试完成")


if __name__ == "__main__":
    asyncio.run(main())
