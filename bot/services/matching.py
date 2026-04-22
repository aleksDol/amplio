import math


def calculate_range(subscribers: int) -> tuple[int, int]:
    min_val = math.floor(subscribers * 0.8)
    max_val = math.ceil(subscribers * 1.2)
    return min_val, max_val
