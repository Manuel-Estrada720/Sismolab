from decimal import Decimal, InvalidOperation


def to_tenths(value) -> int:
    """Convert a decimal value (e.g. "5.2" or 5.2) to tenths (52)
    Rejects non-finite numbers and values with more than one decimal"""
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"Invalid number: {value!r}")
    if not number.is_finite():
        raise ValueError("Number must be finite")
    scaled = number * 10
    if scaled != scaled.to_integral_value():
        raise ValueError("At most one decimal is allowed")
    return int(scaled)