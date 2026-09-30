from dataclasses import dataclass


@dataclass(frozen=True)
class EventData:
    # Physical data of an earthquake. Decimals are stored as tenths (5.2 -> 52)
    id: int            # 1..999999
    magnitude10: int   # -20..100   (M between -2.0 and 10.0)
    depth10: int       # 0..7000    (H between 0.0 and 700.0 km)
    x10: int           # 0..10000   (x between 0.0 and 1000.0 km)
    y10: int           # 0..10000
    time_epoch: int    # seconds since 1970, UTC

    def __post_init__(self):
        if not 1 <= self.id <= 999999:
            raise ValueError("ID must be between 1 and 999999")
        if not -20 <= self.magnitude10 <= 100:
            raise ValueError("Magnitude must be between -2.0 and 10.0")
        if not 0 <= self.depth10 <= 7000:
            raise ValueError("Depth must be between 0.0 and 700.0 km")
        if not (0 <= self.x10 <= 10000 and 0 <= self.y10 <= 10000):
            raise ValueError("Coordinates must be between 0.0 and 1000.0 km")