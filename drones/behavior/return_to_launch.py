"""Return-to-launch behavior helpers."""

from .constants import RTL_SPEED


async def rtl(drone):
    """Command the vehicle to return-to-launch with a conservative current speed."""
    try:
        await drone.action.set_current_speed(RTL_SPEED)
    except Exception:
        pass
    await drone.action.return_to_launch()
