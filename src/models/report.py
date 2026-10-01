class Report:
    # A report sent by a station. It carries the complete event data

    def __init__(self, data, revision, station):
        if revision < 1:
            raise ValueError("Revision must be a positive integer")
        self.data = data            # EventData (already validated)
        self.revision = revision
        self.station = station      # name of the station that sends it