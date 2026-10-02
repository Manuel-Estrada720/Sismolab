class EventData:
    # Physical data of an earthquake. Decimals are stored as tenths (5.2 -> 52)

    def __init__(self, event_id, magnitude10, depth10, x10, y10, time_epoch):
        # Validate before saving anything
        if not 1 <= event_id <= 999999:
            raise ValueError("Id must be between 1 and 999999")
        if not -20 <= magnitude10 <= 100:
            raise ValueError("Magnitude must be between -2.0 and 10.0")
        if not 0 <= depth10 <= 7000:
            raise ValueError("Depth must be between 0.0 and 700.0 km")
        if not (0 <= x10 <= 10000 and 0 <= y10 <= 10000):
            raise ValueError("Coordinates must be between 0.0 and 1000.0 km")

        self.event_id = event_id
        self.magnitude10 = magnitude10
        self.depth10 = depth10
        self.x10 = x10
        self.y10 = y10
        self.time_epoch = time_epoch   # seconds since 1970, UTC

    def __eq__(self, other):
        # Two events have the same data if all these values match
        if not isinstance(other, EventData):
            return False
        return (self.event_id == other.event_id
                and self.magnitude10 == other.magnitude10
                and self.depth10 == other.depth10
                and self.x10 == other.x10
                and self.y10 == other.y10
                and self.time_epoch == other.time_epoch)