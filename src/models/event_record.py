# Attention status
PENDING = "PENDING"
REVIEWED = "REVIEWED"

# Life state
ACTIVE = "ACTIVE"
ARCHIVED = "ARCHIVED"
DELETED = "DELETED"


class EventRecord:
    # Everything the system knows about one earthquake

    def __init__(self, data, revision, priority, station):
        self.data = data              # EventData (physical data)
        self.revision = revision      # current revision
        self.priority = priority      # derived, never typed by the user
        self.stations = [station]     # stations with accepted reports
        self.attention = PENDING      # a new event starts pending
        self.state = ACTIVE

    def key(self):
        # The AVL key K = (P, M, I)
        return (self.priority, self.data.magnitude10, self.data.event_id)

    def add_station(self, station):
        # Add the station if it is not there yet. Returns True if added
        if station in self.stations:
            return False
        self.stations.append(station)
        return True