"""Behavior package exposing flight-phase and formation helpers."""

from .constants import ALT_TKOF, CHECK_INT, LEG_DIST, REACH_R, TRAIL_DIST
from .follower import follower_task
from .landing import land
from .leader import leader_patrol_task
from .return_to_launch import rtl
from .strike import extract_starlink_target, starlink_strike_task
# from .strike_with_cam import starlink_strike_task, extract_starlink_target
from .takeoff import arm_and_takeoff
from .telemetry import push_basic_telemetry
