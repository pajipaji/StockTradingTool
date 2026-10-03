import math


def to_yi(value):
    try:
        result = float(value) / 1e8
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return round(result, 2)


def pct(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return round(result, 2)
