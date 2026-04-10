#!/usr/bin/env python3

import asyncio

from mavsdk import System
from mavsdk.param import ParamError

from behavior import TRAIL_DIST
from behavior.telemetry import push_basic_telemetry
from bridge import FGCBridge
from cmd_process import VALID_FORM_TYPES, cmd_listener
from config import UAV_CFGS
from utils import normalize_group

GUI_PORT = 56999


TRIGGER_SPEED_CHANGE = True 
async def apply_startup_params(drone):
    # 四旋翼默认 MPC_XY_CRUISE=5.0，实飞降速，改为 constants 中默认的巡航速度
    # 注意！固定翼用的是 FW_AIRSPD_TRIM 来控制速度，这个是固定翼控制器的核心量，可以作为实时控制，因此可以在follower里动态调整
    # 注意！而 MPC_XY_CRUISE 只是四旋翼的一个参数，不能频繁改动，否则可能会引起控制不稳定，建议在启动时设置一次，之后保持不变
    # 注意！！！如果要在固定翼上测试，记得注释掉 drones-formation/runtime.py 里 run_drone() 中的 apply_startup_params() 调用！！！
    try:
        await drone.param.set_param_float("MPC_XY_CRUISE", 3.0)
        print("startup param set: MPC_XY_CRUISE=3.0")
    except ParamError as exc:
        print(f"failed to set MPC_XY_CRUISE: {exc}")



def _lookup_cfg(uav_id):
    for cfg in UAV_CFGS:
        try:
            cfg_id = int(cfg.get("id", -1))
        except (TypeError, ValueError):
            continue
        if cfg_id == uav_id:
            return cfg
    raise KeyError(f"未找到编号为 {uav_id} 的无人机配置")


def get_cfg(my_index):
    cfg = dict(_lookup_cfg(my_index))
    cfg.setdefault("id", my_index)
    cfg.setdefault("index", my_index)
    group_value = normalize_group(cfg.get("group", 0))
    if group_value is None:
        group_value = 0
    cfg["group"] = group_value
    bind_ip = "0.0.0.0"
    cmd_port = int(cfg.get("cmd_port", 0))
    gui_host = cfg.get("gui_host", "127.0.0.1")
    gui_port = int(cfg.get("gui_port", GUI_PORT))
    return cfg, bind_ip, cmd_port, gui_host, gui_port


async def connect_uav(cfg):
    drone = System(port=cfg["grpc"])
    print(cfg["ctl"])
    await drone.connect(system_address=f"udp://:{cfg['ctl']}")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            break
    return drone


async def run_drone(uav_id):
    """Bootstrap a single drone instance with group-aware command handling."""
    try:
        cfg, bind_ip, cmd_port, gui_host, gui_port = get_cfg(uav_id)
    except KeyError as exc:
        raise RuntimeError(f"未找到无人机 {uav_id} 的配置") from exc
    drone = await connect_uav(cfg)
    if TRIGGER_SPEED_CHANGE==True:
        await apply_startup_params(drone) 


    role = str(cfg.get("role", "")).strip().lower()
    is_leader = role == "leader" or bool(int(cfg.get("is_leader", 0)))

    drone_id = int(cfg.get("id", uav_id))
    bridge_name = cfg.get("tag", "LEAD" if is_leader else f"DRONE{drone_id}")

    # peers 在 formation_start 时由 _start_formation_task 动态设置为编队成员
    bridge = FGCBridge(
        bind_ip=bind_ip,
        bind_port=cmd_port,
        gui_host=gui_host,
        gui_port=gui_port,
        peers=None,
        name=bridge_name,
    )

    await bridge.start()
    bridge.patch_print()

    telemetry_tag = cfg.get("tag", bridge_name)
    telemetry_idx = drone_id
    asyncio.create_task(push_basic_telemetry(drone, bridge, tag=telemetry_tag, idx=telemetry_idx))

    raw_type = cfg.get("formation_types", cfg.get("form_type", 1))
    try:
        form_type = int(raw_type)
    except (TypeError, ValueError):
        form_type = 1
    if form_type not in VALID_FORM_TYPES:
        form_type = 1

    raw_spacing = cfg.get("formation_spacing", cfg.get("spacing", TRAIL_DIST))
    try:
        spacing = float(raw_spacing)
    except (TypeError, ValueError):
        spacing = TRAIL_DIST
    if spacing <= 0:
        spacing = TRAIL_DIST

    form_ref = {
        "type": form_type,
        "spacing": spacing,
    }
    tasks = []
    listener = asyncio.create_task(
        cmd_listener(bridge, tasks, drone, form_ref, cfg)
    )

    print(f"[{bridge_name}] ready on {bind_ip}:{cmd_port}, GUI={gui_host}:{gui_port}")

    await listener
