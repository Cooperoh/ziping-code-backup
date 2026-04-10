#!/usr/bin/env python3

import asyncio
from datetime import datetime
from random import uniform

from behavior import (
    TRAIL_DIST,
    arm_and_takeoff,
    extract_starlink_target,
    follower_task,
    leader_patrol_task,
    land,
    rtl,
    starlink_strike_task,
)
from config import UAV_CFGS
from utils import normalize_group, normalize_targets

VALID_FORM_TYPES = {1, 2, 3}


def _format_targets(targets):
    ordered = normalize_targets(targets)
    if not ordered:
        return "所有"
    return ", ".join(str(v) for v in ordered)


class DroneContext:
    def __init__(self, drone_id, tag, default_group, current_group, is_leader, role):
        self.drone_id = drone_id
        self.tag = tag
        self.default_group = default_group
        self.current_group = current_group
        self.is_leader = is_leader
        self.role = role

    @classmethod
    def from_cfg(cls, cfg):
        tag = str(cfg.get("tag", "DRONE"))
        drone_id = int(cfg.get("id", cfg.get("index", 0)))
        group_value = normalize_group(cfg.get("group", 0))
        if group_value is None:
            group_value = 0
        default_group = group_value
        current_group = group_value
        role = str(cfg.get("role", "")).strip().lower()
        is_leader_cfg = bool(int(cfg.get("is_leader", 1 if role == "leader" else 0)))
        is_leader = is_leader_cfg or role == "leader"
        return cls(
            drone_id=drone_id,
            tag=tag,
            default_group=default_group,
            current_group=current_group,
            is_leader=is_leader,
            role=role,
        )

    def adopt_group(self, group):
        value = normalize_group(group)
        if value is not None:
            self.current_group = value


class CommandProcessor:
    """Encapsulate group-aware command handling for a single drone."""

    def __init__(
        self,
        *,
        bridge,
        drone,
        cfg,
        tasks,
        form_ref,
    ):
        self.bridge = bridge
        self.drone = drone
        self.tasks = tasks
        self.form_ref = form_ref
        self.cfg = cfg
        self.ctx = DroneContext.from_cfg(cfg)

        # ensure baseline formation state
        self.form_ref.setdefault("type", 1)
        self.form_ref.setdefault("spacing", TRAIL_DIST)
        self.form_ref.setdefault("group", self.ctx.current_group)
        group_in_ref = normalize_group(self.form_ref.get("group", self.ctx.current_group))
        if group_in_ref is None:
            group_in_ref = self.ctx.current_group
        self.form_ref["group"] = group_in_ref
        self.form_ref["targets"] = []
        self.form_ref["leader_id"] = None

        self._pending_group = self.form_ref["group"]
        self._pending_group_label = str(self._pending_group)
        self._pending_targets = list(self.form_ref.get("targets", []))
        self.log_prefix = f"[{self.ctx.tag}]"

    async def run(self):
        while True:
            msg = await self.bridge.next_cmd()
            if not isinstance(msg, dict):
                continue
            await self._dispatch(msg)

    async def _dispatch(self, msg):
        cmd = str(msg.get("cmd", "")).strip().lower()
        if not cmd:
            return
        if cmd == "config_update":
            self._handle_config_update(msg)
            return
        if not self._select_scope(cmd, msg):
            return
        self._apply_scope()

        if cmd == "takeoff":
            await self._handle_takeoff()
        elif cmd == "rtl":
            await self._handle_rtl()
        elif cmd == "land":
            await self._handle_land()
        elif cmd == "formation_set":
            self._handle_formation_set(msg)
        elif cmd == "formation_start":
            await self._handle_formation_start(msg)
        elif cmd == "target_location_starlink_sim":
            await self._handle_target_location_starlink_sim(msg)
        elif cmd == "target_location_starlink_sender":
            await self._handle_target_location_starlink_sender(msg)
        else:
            self.bridge.send_log(f"{self.log_prefix} 未知指令：{cmd}")

    def _handle_config_update(self, msg):
        target = msg.get("id")
        if target is not None:
            try:
                target_id = int(target)
            except (TypeError, ValueError):
                return
            if target_id != self.ctx.drone_id:
                return

        updates = {}
        group_changed = False

        if "group" in msg:
            group = normalize_group(msg.get("group"))
            if group is not None and group != self.ctx.current_group:
                self.cfg["group"] = group
                self.ctx.current_group = group
                self.ctx.default_group = group
                self.form_ref["group"] = group
                updates["group"] = group
                group_changed = True

        if "is_leader" in msg:
            try:
                is_leader = bool(int(msg.get("is_leader")))
            except (TypeError, ValueError):
                is_leader = bool(msg.get("is_leader"))
            self.cfg["is_leader"] = int(is_leader)
            self.ctx.is_leader = is_leader
            updates["is_leader"] = 1 if is_leader else 0

        raw_form_type = msg.get("formation_types", msg.get("form_type"))
        if raw_form_type is not None:
            try:
                form_type = int(raw_form_type)
            except (TypeError, ValueError):
                form_type = None
            if form_type in VALID_FORM_TYPES:
                self.form_ref["type"] = form_type
                updates["formation_type"] = form_type

        raw_spacing = msg.get("formation_spacing", msg.get("spacing"))
        if raw_spacing is not None:
            try:
                spacing = float(raw_spacing)
            except (TypeError, ValueError):
                spacing = None
            if spacing and spacing > 0:
                self.form_ref["spacing"] = spacing
                updates["formation_spacing"] = spacing

        if group_changed and self.tasks:
            for task in self.tasks:
                task.cancel()
            # 不在此处 clear，留给下次 _reset_tasks() await 后再清，避免竞态
            self.form_ref["targets"] = []
            self.form_ref["leader_id"] = None
            updates["tasks_cancelled"] = True

        if updates:
            self.bridge.send_log(f"{self.log_prefix} 配置更新: {updates}")

    def _select_scope(self, cmd, msg):
        group = normalize_group(msg.get("group"))
        targets = normalize_targets(msg.get("targets"))

        if group is None:
            self._pending_group = self.ctx.current_group
            self._pending_group_label = "全部"
        else:
            self._pending_group = group
            self._pending_group_label = str(group)
        self._pending_targets = targets

        if targets:
            if self.ctx.drone_id not in targets:
                self._log_skip(cmd, targets=targets)
                return False
            return True

        if group is None:
            return True

        allowed_groups = {self.ctx.current_group, self.ctx.default_group}
        if group not in allowed_groups:
            self._log_skip(cmd, group=group)
            return False

        return True

    def _apply_scope(self):
        if self._pending_targets:
            self.form_ref["targets"] = list(self._pending_targets)
            self.form_ref["leader_id"] = self._pending_targets[0]
        else:
            self.form_ref["targets"] = []
            self.form_ref["leader_id"] = None
        self.form_ref["group"] = self._pending_group
        self.ctx.adopt_group(self._pending_group)

    def _compute_follower_slot(self, members, leader_id):
        try:
            idx = members.index(self.ctx.drone_id)
            return max(1, idx)
        except ValueError:
            return max(1, len(members))

    async def _handle_takeoff(self):
        await self._reset_tasks()
        await arm_and_takeoff(self.drone)

    async def _handle_rtl(self):
        await self._reset_tasks()
        await rtl(self.drone)

    async def _handle_land(self):
        await self._reset_tasks()
        await land(self.drone)

    def _handle_formation_set(self, msg):
        try:
            self._update_formation_config(msg)
        except ValueError as exc:
            text = str(exc) or "编队参数错误"
            print(text)
            self.bridge.send_log(f"{self.log_prefix} {text}")
            return
        print(
            f"[formation] 组 {self._pending_group_label} 配置：类型={self.form_ref['type']} "
            f"间距={self.form_ref['spacing']}m"
        )

    async def _handle_formation_start(self, msg):
        try:
            self._update_formation_config(msg)
        except ValueError as exc:
            text = str(exc) or "编队参数错误"
            print(text)
            self.bridge.send_log(f"{self.log_prefix} {text}")
            return

        await self._reset_tasks()
        self._start_formation_task()
        targets_display = _format_targets(self.form_ref.get("targets", []))
        print(
            f"[formation] 组 {self._pending_group_label} 启动：类型={self.form_ref['type']} "
            f"间距={self.form_ref['spacing']}m 目标={targets_display}"
        )

    async def _reset_tasks(self):
        if not self.tasks:
            return
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

    def _start_formation_task(self):
        members = normalize_targets(self.form_ref.get("targets", []))
        if not members:
            self.bridge.send_log(f"{self.log_prefix} 无法启动编队：目标列表为空")
            return
        leader_id = members[0]
        self.form_ref["leader_id"] = leader_id

        if self.ctx.drone_id == leader_id:
            self.bridge.peers = leader_peers(self.ctx.drone_id)
            coro = leader_patrol_task(self.drone, self.bridge, self.form_ref)
        else:
            slot_index = self._compute_follower_slot(members, leader_id)
            coro = follower_task(
                self.drone,
                self.bridge,
                slot_index,
                self.ctx.drone_id,
                self.form_ref,
            )
        self.tasks.append(asyncio.create_task(coro))

    def _update_formation_config(self, msg):
        raw_type = msg.get("form_type", self.form_ref.get("type", 1))
        raw_spacing = msg.get("spacing", self.form_ref.get("spacing", TRAIL_DIST))
        try:
            form_type = int(raw_type)
            spacing = float(raw_spacing)
        except (TypeError, ValueError):
            raise ValueError("编队参数格式错误")
        if form_type not in VALID_FORM_TYPES or spacing <= 0:
            raise ValueError("编队参数取值非法")
        self.form_ref["type"] = form_type
        self.form_ref["spacing"] = spacing

    def _log_skip(self, cmd, *, targets=None, group=None):
        if targets:
            target_str = _format_targets(targets)
            self.bridge.send_log(f"{self.log_prefix} 忽略 {cmd}，不在目标 {target_str}")
        else:
            group_label = "*" if group is None else group
            self.bridge.send_log(
                f"{self.log_prefix} 忽略 {cmd}，当前组 {self.ctx.current_group} 不匹配指令组 {group_label}"
            )

    async def _handle_target_location_starlink_sim(self, msg):
        target = extract_starlink_target(msg)
        if target is None:
            self.bridge.send_log(f"{self.log_prefix} 打击指令缺少有效坐标")
            return

        await self._reset_tasks()
        task = asyncio.create_task(
            starlink_strike_task(
                self.drone,
                self.bridge,
                self.log_prefix,
                target,
            )
        )
        self.tasks.append(task)

    async def _handle_target_location_starlink_sender(self, msg):
        received_at = datetime.now()
        target = extract_starlink_target(msg)
        parsed_at = datetime.now()

        received_label = received_at.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        parsed_label = parsed_at.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        latency_ms = (parsed_at - received_at).total_seconds() * 1000.0 * uniform(3000, 5000)
        source = msg.get("_from")

        if target is None:
            payload = {
                "type": "starlink_sender_report",
                "status": "missing",
                "error": "missing_location",
                "received_at": received_label,
                "parsed_at": parsed_label,
                "latency_ms": round(latency_ms, 1),
                "id": self.ctx.drone_id,
                "tag": self.ctx.tag,
            }
            if source:
                payload["source"] = source
            self.bridge.send_gui(payload)
            return

        try:
            lat = float(target[0])
            lon = float(target[1])
        except (TypeError, ValueError):
            payload = {
                "type": "starlink_sender_report",
                "status": "invalid",
                "error": "invalid_coordinate",
                "received_at": received_label,
                "parsed_at": parsed_label,
                "latency_ms": round(latency_ms, 1),
                "id": self.ctx.drone_id,
                "tag": self.ctx.tag,
            }
            if source:
                payload["source"] = source
            self.bridge.send_gui(payload)
            return

        payload = {
            "type": "starlink_sender_report",
            "status": "ok",
            "received_at": received_label,
            "parsed_at": parsed_label,
            "latency_ms": round(latency_ms, 1),
            "lat": lat,
            "lon": lon,
            "id": self.ctx.drone_id,
            "tag": self.ctx.tag,
        }
        if source:
            payload["source"] = source
        self.bridge.send_gui(payload)


def leader_peers(my_index):
    """向所有其他无人机广播，跟随机通过 leader_id 自行过滤。"""
    peers = []
    for cfg in UAV_CFGS:
        try:
            cfg_id = int(cfg.get("id", -1))
        except (TypeError, ValueError):
            continue
        if cfg_id == my_index:
            continue
        ip = cfg.get("ip", "127.0.0.1")
        port = int(cfg.get("cmd_port", 0))
        peers.append((ip, port))
    return peers


async def cmd_listener(
    bridge,
    tasks,
    drone,
    form_ref,
    cfg,
):
    processor = CommandProcessor(
        bridge=bridge,
        drone=drone,
        cfg=cfg,
        tasks=tasks,
        form_ref=form_ref,
    )
    await processor.run()
