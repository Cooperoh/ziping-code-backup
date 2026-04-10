"""Landing helpers."""


async def land(drone):
    """Command a landing sequence."""
    await drone.action.land()
