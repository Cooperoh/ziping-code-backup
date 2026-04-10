#!/usr/bin/env python3
"""Utility helpers for geodesy computations and formation offsets."""

import math
from math import cos, radians

from geopy import Point, distance
from geopy.distance import geodesic

SQRT3_2 = math.sqrt(3) / 2
MAX_FORMATION_SIZE = 24


# 将距离转换为纬度lat和经度lon（替换原函数offset）
def calculate_new_coordinates(lat, lon, north_m, east_m):
    """
    计算从给定坐标点 (lat, lon) 出发，沿正北/正南和正东/正西方向移动指定距离后的新坐标点。
    支持正北/正南、正东/正西四象限位移：
    - north_m  >0 向北，<0 向南
    - east_m   >0 向东，<0 向西
    """
    origin = Point(lat, lon)

    # 先沿南北方向
    if north_m:
        bearing_ns = 0 if north_m > 0 else 180
        origin = geodesic(meters=abs(north_m)).destination(origin, bearing_ns)

    # 再沿东西方向
    if east_m:
        bearing_ew = 90 if east_m > 0 else 270
        origin = geodesic(meters=abs(east_m)).destination(origin, bearing_ew)

    return round(origin.latitude, 7), round(origin.longitude, 7)


# 计算两个纬度lat和经度lon距离（替换原函数dist_m）
def calculate_positions_distance(x1, y1, x2, y2):
    """计算两个坐标点 (x1, y1) 和 (x2, y2) 之间的地理距离，单位米。"""
    return distance.distance((x1, y1), (x2, y2)).m


# 计算目标点相对于基准点的东西南北距离
def calculate_relative_distance(lat, lon, ref_lat, ref_lon, earth_radius=6378137.0):
    """
    计算坐标点 (lat, lon) 相对于参考点 (ref_lat, ref_lon) 的
    向北距离 north 和向东距离 east。

    参数
    ----
    lat, lon        : 目标点的纬度、经度 (度)
    ref_lat, ref_lon: 参考点的纬度、经度 (度)
    earth_radius    : 地球半径 (米)，默认值为 6378137.0 米
    返回
    ----
    north : float   向北位移，单位 m；北为正，南为负
    east  : float   向东位移，单位 m；东为正，西为负
    """
    # 经纬度差换算成弧度
    d_lat = radians(lat - ref_lat)
    d_lon = radians(lon - ref_lon)

    # 参考纬度（或两点纬度平均）转弧度，用于计算东西向缩放
    mean_lat = radians((lat + ref_lat) / 2.0)

    # 向北、向东位移
    north = d_lat * earth_radius
    east = d_lon * earth_radius * cos(mean_lat)

    return north, east


def _triangle_offset(index, spacing):
    level = 1
    remaining = index
    while True:
        drones_in_level = level + 1
        if remaining <= drones_in_level:
            slot = remaining - 1
            lateral = (slot - (drones_in_level - 1) / 2.0) * spacing
            longitudinal = -level * SQRT3_2 * spacing
            return longitudinal, lateral
        remaining -= drones_in_level
        level += 1


def get_offset(index, form_type, spacing):
    """
    Compute the body-frame offset for followers relative to the leader.
    Supports up to MAX_FORMATION_SIZE aircraft (excluding the leader).
    """
    if index <= 0 or spacing <= 0 or index > MAX_FORMATION_SIZE:
        return 0.0, 0.0

    if form_type == 1:  # triangle
        return _triangle_offset(index, spacing)

    if form_type == 2:  # line abreast (leader centered, followers alternate left/right)
        rank = (index + 1) // 2
        side = -1 if index % 2 == 1 else 1
        return -0.5 * spacing, side * rank * spacing

    if form_type == 3:  # straight trail
        return -index * spacing, 0.0

    return 0.0, 0.0


def normalize_group(value):
    """将 group 字段规范化为 int 或 None（None 表示"全部"）。"""
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.lower() == "all":
            return None
        try:
            return int(raw, 10)
        except ValueError:
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_targets(raw):
    """将 targets 字段规范化为去重的 int 列表。"""
    if raw is None or isinstance(raw, (str, bytes)):
        return []
    try:
        iterator = iter(raw)
    except TypeError:
        return []
    result = []
    seen = set()
    for item in iterator:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def safe_float(value, default):
    """将 value 转换为有限浮点数，失败时返回 default。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(parsed):
        return float(default)
    return parsed


def resolve_goto_absolute_altitude(position, target_relative_alt_m):
    """
    将相对 home 点的目标高度换算为 goto_location() 所需的 AMSL 绝对海拔。

    如果当前遥测缺少 relative_altitude_m，则保守地维持当前 absolute_altitude_m，
    避免把相对高度误当成绝对海拔直接下发。
    """
    target_rel = safe_float(target_relative_alt_m, 0.0)

    absolute_alt = getattr(position, "absolute_altitude_m", None)
    if not isinstance(absolute_alt, (int, float)) or not math.isfinite(absolute_alt):
        raise ValueError("position sample missing absolute_altitude_m")
    absolute_alt = float(absolute_alt)

    relative_alt = getattr(position, "relative_altitude_m", None)
    if not isinstance(relative_alt, (int, float)) or not math.isfinite(relative_alt):
        return absolute_alt

    home_absolute_alt = absolute_alt - float(relative_alt)
    return home_absolute_alt + target_rel


if __name__ == "__main__":

    # 基准点 (纬度, 经度)
    base_point = (40.7128, -74.0060)  # 纽约
    # 目标点 (纬度, 经度)
    target_point = (40.6130, -75.0058)  # 纽约附近某点

    n, e = calculate_relative_distance(*target_point, *base_point)  # 前面减后面

    d = calculate_positions_distance(*target_point, *base_point)

    print(n, e, d)
