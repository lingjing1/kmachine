from datetime import datetime, timezone, timedelta

# Taipei Timezone (UTC+8)
TAIPEI_TZ = timezone(timedelta(hours=8))

def get_now_taipei() -> datetime:
    """
    Returns the current Taipei time as a naive datetime object.
    This ensures that database timestamps are consistently stored as Taipei time
    without timezone info, avoiding confusion between UTC and local time.
    """
    return datetime.now(TAIPEI_TZ).replace(tzinfo=None)

def to_taipei_naive(dt: datetime) -> datetime:
    """
    Converts a datetime object (with or without tz) to Taipei time naive datetime.
    """
    if dt.tzinfo is None:
        # Assume naive is already Taipei or convert from local if needed?
        # Standardize: if naive, treat as Taipei or re-localize carefully.
        # For now, let's assume if it has no tz, we don't know, but if it has tz, we convert.
        return dt
    return dt.astimezone(TAIPEI_TZ).replace(tzinfo=None)
