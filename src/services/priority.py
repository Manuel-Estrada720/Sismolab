from ..models.event_data import EventData
from ..models.zone import ZoneMap

HIGH, MEDIUM, LOW = 3, 2, 1

def calculate_priority(data: EventData, zones: ZoneMap) -> int:
    # Return 3 (high), 2 (medium) or 1 (low). Limits are inclusive
    populated = zones.is_populated(data.x10, data.y10)
    # Priority is calculated according to the rules in the following order
    if data.magnitude10 >= 60:                                   # M >= 6.0
        return HIGH
    if data.magnitude10 >= 45 and data.depth10 <= 300 and populated:
        return HIGH                                              # M >= 4.5, H <= 30.0, populated
    if data.magnitude10 >= 45:                                   # M >= 4.5
        return MEDIUM
    return LOW