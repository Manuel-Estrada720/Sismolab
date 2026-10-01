class EventRegistry:
    # All the events the system has ever known: active, archived and deleted

    def __init__(self):
        self.records = {}     # {event_id: EventRecord}

    def get(self, event_id):
        # Return the record, or None if the id is unknown
        return self.records.get(event_id)

    def add(self, record):
        self.records[record.data.event_id] = record

    def count_by_state(self, state):
        total = 0
        for record in self.records.values():
            if record.state == state:
                total += 1
        return total