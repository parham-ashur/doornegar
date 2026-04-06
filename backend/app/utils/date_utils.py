"""Date utilities for Jalali/Gregorian conversion."""

from datetime import datetime

import jdatetime


def to_jalali(dt: datetime) -> str:
    """Convert a datetime to Jalali date string (e.g., '۱۴۰۴/۰۱/۱۷')."""
    if dt is None:
        return ""
    jalali = jdatetime.datetime.fromgregorian(datetime=dt)
    return jalali.strftime("%Y/%m/%d")


def to_jalali_full(dt: datetime) -> str:
    """Convert to full Jalali date (e.g., '۱۷ فروردین ۱۴۰۴')."""
    if dt is None:
        return ""
    jalali = jdatetime.datetime.fromgregorian(datetime=dt)
    return jalali.strftime("%d %B %Y")


def relative_time_fa(dt: datetime) -> str:
    """Get a Farsi relative time string (e.g., '۲ ساعت پیش')."""
    if dt is None:
        return ""
    now = datetime.now(dt.tzinfo)
    diff = now - dt
    seconds = int(diff.total_seconds())

    if seconds < 60:
        return "لحظاتی پیش"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} دقیقه پیش"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} ساعت پیش"
    elif seconds < 604800:
        days = seconds // 86400
        return f"{days} روز پیش"
    else:
        return to_jalali(dt)
