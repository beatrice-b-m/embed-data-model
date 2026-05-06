import math


def get_point_on_line(
    origin_point: tuple[float, float], slope: float, distance: float
) -> tuple[float, float]:
    x0, y0 = origin_point

    if math.isinf(slope):
        x1: float = x0
        y1: float = y0 + distance
        return (x1, y1)

    denominator: float = math.sqrt(1 + slope**2)

    delta_x: float = distance / denominator
    delta_y: float = (slope * distance) / denominator

    # Calculate the new point
    x1: float = x0 + delta_x
    y1: float = y0 + delta_y

    return (x1, y1)


# def get_uuid() -> str:
#     return uuid.uuid4().hex
