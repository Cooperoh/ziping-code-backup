"""编队行为共享常量。"""

# 起飞目标相对高度（相对 home 点，单位 m）。
# 注意：set_takeoff_altitude() 使用相对高度；goto_location() 需要先换算成 AMSL 绝对海拔。
# utils.resolve_goto_absolute_altitude() 提供了让无人机维持在home点绝对海拔高度以上ALT_TKOF米的方法。
# 也可以直接记下 base_abs_alt = pos.absolute_altitude_m，之后整段飞行都以 base_abs_alt + ALT_TKOF 作为 goto_location() 的高度参数。
ALT_TKOF = 10

LEG_DIST = 100.0                    # 领机巡逻每一段的目标腿长
TRAIL_DIST = 10.0                   # 跟随机尾随领机的名义间距
REACH_R = 10.0                      # 判定到达目标点的半径

CHECK_INT = 0.5                     # 控制循环检查周期

CRUISE_SPEED = 3                    # 默认巡航速度

FOLLOW_SPEED_BASE = 3               # 跟随模式基准速度
FOLLOW_SPEED_MIN = 0.1              # 跟随速度下限
FOLLOW_SPEED_MAX = 6.0              # 跟随速度上限
FOLLOW_SPEED_GAIN = 0.30            # 速度修正增益：越大则对前后误差修正越激进（当前0.12对应25m，0.30对应10m，0.50对应6m）

RTL_SPEED = 5                       # 返航前设置的保守速度

ARM_DELAY = 0.5                     # 解锁后等待时间
TAKEOFF_DELAY = 1.0                 # 发送起飞指令后的初始等待
ALT_WAIT_TIMEOUT = 10.0             # 等待达到起飞高度的超时时间
ALT_TOLERANCE = 2.0                 # 达高判定容差
ALT_CHECK_INTERVAL = 0.5            # 高度检查周期

FOLLOW_ERR_DEADBAND = 0.8           # 前后误差死区（米）：误差很小时不修速，避免频繁抖动

LOOKAHEAD_SPACING_GAIN = 1.2        # 前视距离中的 编队间距项 系数：spacing * 该值
LOOKAHEAD_SPEED_TIME = 1.5          # 前视距离中的 速度项时间窗 （秒）：lead_speed * 该值

LOOKAHEAD_MIN = 6.0                 # 前视距离下限（米）：低速时也保持足够前视，避免小步频繁追点，对固定翼来说，最小前视距离必须大于进入盘旋的距离
LOOKAHEAD_MAX = 20.0                # 前视距离上限（米）：防止前视点过远导致跟随响应过慢

# follower里面的速度判断条件
# 固定翼模式下，更需要计算速度、前视距离和编队间距的关系，确保编队表现和飞行安全！

# follower代码判断速度指令为以下两条：
# lead_speed - FOLLOW_SPEED_GAIN * fwd_err <= FOLLOW_SPEED_MIN
# lead_speed - FOLLOW_SPEED_GAIN * fwd_err >= FOLLOW_SPEED_MAX

# 这两条不等式可以化简为：
# fwd_err >= (lead_speed - FOLLOW_SPEED_MIN) / FOLLOW_SPEED_GAIN
# fwd_err <= (lead_speed - FOLLOW_SPEED_MAX) / FOLLOW_SPEED_GAIN

# 如果领机速度lead_speed = 3m/s
# 当fwd_err >= (3 - 0) / 0.12 =  25m时，跟机速度将被限制在FOLLOW_SPEED_MIN = 0 m/s
# 当fwd_err <= (3 - 6) / 0.12 = -25m时，跟机速度将被限制在FOLLOW_SPEED_MAX = 6 m/s

# 通过增加FOLLOW_SPEED_GAIN，可以让跟机更激进地修正前后误差（米）
# 通过增加FOLLOW_ERR_DEADBAND，可以扩大前后误差的死区范围
# 注意，fwd_err不是绝对值，它跟lead_speed绑定，因此在领机速度较高时，允许的前后误差范围也会相应增加


def quick_calculate_speed_vs_err():
    """快速计算给定领机速度和速度修正增益时的最大前后误差"""
    max_fwd_err = (CRUISE_SPEED - FOLLOW_SPEED_MIN) / FOLLOW_SPEED_GAIN
    min_fwd_err = (CRUISE_SPEED - FOLLOW_SPEED_MAX) / FOLLOW_SPEED_GAIN
    lead_speed, fol_speed_min, fol_speed_max, fol_gain = 3, 0.1, 6, 0.12
    max_fwd_err = (lead_speed - fol_speed_min) / fol_gain
    min_fwd_err = (lead_speed - fol_speed_max) / fol_gain
    print(max_fwd_err, min_fwd_err)

def quick_compare_speed_vs_err():
    """快速比较不同参数设置下的最大前后误差"""
    for gain in [0.50]:
        max_err = (CRUISE_SPEED - FOLLOW_SPEED_MIN) / gain
        min_err = (CRUISE_SPEED - FOLLOW_SPEED_MAX) / gain
        print(max_err, min_err)

if __name__ == "__main__":
    quick_calculate_speed_vs_err()
    # quick_compare_speed_vs_err()
    