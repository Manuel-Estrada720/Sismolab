from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def to_tenths(value) -> int:
    """Convert a decimal value (e.g. "5.2" or 5.2) to tenths (52)
    Rejects non-finite numbers and values with more than one decimal"""
    if isinstance(value, bool):
        raise ValueError(f"Número inválido: {value!r}")
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"Número inválido: {value!r}")
    if not number.is_finite():
        raise ValueError("El número debe ser finito")
    scaled = number * 10
    if scaled != scaled.to_integral_value():
        raise ValueError(f"El valor {value} tiene más de un decimal")
    return int(scaled)


def from_tenths(tenths: int):
    """Convert tenths back to a number for JSON and the GUI (52 -> 5.2)."""
    if tenths % 10 == 0:
        return tenths // 10
    return tenths / 10


def parse_utc(text) -> int:
    """Convert an ISO 8601 UTC text ("2026-09-07T10:00:00Z") to epoch seconds."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("La fecha debe ser un texto ISO 8601, por ejemplo 2026-09-07T10:00:00Z")
    clean = text.strip()
    if clean.endswith("Z") or clean.endswith("z"):
        clean = clean[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(clean)
    except ValueError:
        raise ValueError(f"Fecha inválida: {text!r}. Use el formato 2026-09-07T10:00:00Z")
    if moment.tzinfo is None:
        raise ValueError(f"La fecha {text!r} debe estar en UTC (termine en Z)")
    if moment.utcoffset().total_seconds() != 0:
        raise ValueError(f"La fecha {text!r} debe estar en UTC (termine en Z)")
    if moment.microsecond != 0:
        raise ValueError("La fecha solo admite precisión de segundos")
    return int(moment.timestamp())


def format_utc(epoch: int) -> str:
    """Convert epoch seconds to ISO 8601 UTC text."""
    moment = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
