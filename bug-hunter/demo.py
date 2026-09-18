"""A small, clean module for the watch-mode demo. Break something and save."""

import math


def average(values):
    if not values:
        return 0.0
    return sum(values) / len(values)


def in_range(value, low, high):
    """True when low <= value <= high."""
    return low <= value <= high


def to_int(text, default=None):
    try:
        return int(text)
    except ValueError:
        return default


def append_tag(tag, tags=None):
    tags = [] if tags is None else list(tags)
    tags.append(tag)
    return tags


def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def get_user_by_name(conn, name):
    return conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()


def grade(score):
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    return "F"


def is_zero_balance(deposits, withdrawals):
    return math.isclose(sum(deposits) - sum(withdrawals), 0.0, abs_tol=1e-9)
