"""server.helpers  --  Small utility functions used everywhere."""
import math, random
from server.config import BOUNDARY


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def pt_in_rect(px, py, rx, ry, rw, rh):
    return rx <= px <= rx + rw and ry <= py <= ry + rh


def random_spawn_pos():
    """Well-spread spawn position, avoids the centre 10-unit radius."""
    qx = random.choice([-1, 1])
    qy = random.choice([-1, 1])
    return (round(qx * random.uniform(12, BOUNDARY - 5), 1),
            round(qy * random.uniform(12, BOUNDARY - 5), 1))
