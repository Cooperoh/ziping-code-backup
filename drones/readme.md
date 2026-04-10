# 四旋翼兼容改动说明

本次主要目标：移除 `behavior` 中固定翼专用的速度参数/接口，改为四旋翼可用的通用接口。

## 修改文件与内容

### 1) `behavior/telemetry.py`

- 速度读取统一使用 `telemetry.velocity_ned()`。
- 由 `north/east` 速度分量通过 `math.hypot()` 合成水平速度并上报。
- 不再依赖 `fixedwing_metrics().airspeed_m_s`。

示例：

```python
vel = await drone.telemetry.velocity_ned().__anext__()
speed = math.hypot(vel.north_m_s, vel.east_m_s)
```

### 2) `behavior/leader.py`

- 删除固定翼参数设置：`FW_AIRSPD_TRIM`。
- 巡航速度改为尝试 `action.set_current_speed()`（失败则降级为飞控默认速度，不中断任务）。
- 广播给跟随机的 `speed` 改为由 `velocity_ned()` 合成的地速。

### 3) `behavior/follower.py`

- 删除通过 `FW_AIRSPD_TRIM` 调速的固定翼逻辑。
- 改为 `action.set_current_speed()` 动态调速（若飞控不支持，仅记录一次日志并降级为纯航点跟随）。
- 保留原有编队几何与 `goto_location()` 跟随逻辑。

### 4) `behavior/takeoff.py`

- 删除 `FW_AIRSPD_MAX / FW_AIRSPD_TRIM / FW_AIRSPD_MIN` 的设置与读取。
- 起飞后改为尝试通用接口 `action.set_current_speed()`。
- 若不支持该接口，仅打印失败信息，不影响起飞主流程。

### 5) `behavior/return_to_launch.py`

- 删除 RTL 前设置 `FW_AIRSPD_TRIM`。
- 改为 RTL 前尝试 `action.set_current_speed()`，失败则忽略。

### 6) `behavior/strike.py`

- 删除打击任务中的固定翼参数：
  - `FW_AIRSPD_TRIM`
  - `FW_T_SINK_MAX`
- 改为尝试 `action.set_current_speed(CRUISE_SPEED)`，失败降级为默认速度。

## 结果

- `behavior` 主流程已不再依赖固定翼专用 `FW_*` 参数。
- 速度获取/广播统一基于 `velocity_ned()`，可直接用于四旋翼。

---

# 代码重构说明

## 修改内容

### 1) `utils.py` — 新增三个公共工具函数

将散落在各模块中的重复实现统一提取至此：

- `normalize_group(value)` — 将 group 字段规范化为 `int` 或 `None`（原来在 `runtime.py` 和 `cmd_process.py` 中各有一份相同实现）
- `normalize_targets(raw)` — 将 targets 字段规范化为去重 int 列表（原来在 `cmd_process.py` 和 `follower.py` 内部各有一份）
- `safe_float(value, default)` — 安全浮点转换，含 `isfinite` 检查（原来在 `follower.py` 内部定义）

### 2) `runtime.py`

- 删除本地 `_normalize_group` 函数，改为 `from utils import normalize_group`
- 删除多余的中间变量 `is_leader_cfg`，直接赋值给 `is_leader`

### 3) `cmd_process.py`

- 删除本地 `_normalize_group` 和 `_normalize_targets` 函数，改为 `from utils import normalize_group, normalize_targets`
- 简化 `_format_targets`：原来内部重复了去重逻辑，现在直接调用 `normalize_targets` 后 join

### 4) `behavior/follower.py`

- 删除嵌套函数 `_normalize_targets`（局部实现），改为从 `utils` 导入
- 删除嵌套函数 `_safe_float`，改为从 `utils` 导入
- 删除局部包装函数 `_safe_send_follow_telemetry`，直接调用 `bridge.send_telemetry`（`bridge._sendto` 内部已有 try/except，调用本身是安全的）

### 5) `behavior/leader.py`

- 删除局部包装函数 `_safe_send_lead_telemetry`，直接调用 `bridge.send_telemetry`（同上）

### 6) `bridge.py`

- 提取私有方法 `_await_queue(q)`，消除 `next_cmd` / `next_peer` / `next_misc` 三个方法中完全相同的 `asyncio.to_thread` 包装模式

### 7) `drone-exec/` — 合并 12 个重复入口文件

原来 `drone_id_0.py` 至 `drone_id_11.py` 共 12 个文件，内容完全一致，仅 `idx` 数字不同。

**已删除这 12 个文件，替换为单一入口 `drone-exec/run.py`。**

用法：
```bash
python drone-exec/run.py 0   # 启动编号为 0 的无人机
python drone-exec/run.py 3   # 启动编号为 3 的无人机
```
