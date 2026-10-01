class Zone:
    # Rectangular zone. Borders are inclusive. Coordinates in tenths of km

    def __init__(self, zone_id, populated, x1, y1, x2, y2):
        self.zone_id = zone_id
        self.populated = populated    # True or False
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    def contains(self, x10, y10): # True if the point (x10, y10) is inside the zone (border included)
        return (self.x1 <= x10 <= self.x2
                and self.y1 <= y10 <= self.y2)


class ZoneMap:
    # All the zones of the scenario

    def __init__(self, zones):
        self.zones = list(zones)

    def is_populated(self, x10, y10):
        # True if some populated zone contains the point (border included)
        for zone in self.zones:
            if zone.populated and zone.contains(x10, y10):
                return True
        return False