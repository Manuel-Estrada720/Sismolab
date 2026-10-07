class Report:
    # A report sent by a station. It carries the complete event data

    def __init__(self, data, revision, station):
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError("La revisión debe ser un entero positivo")
        if not isinstance(station, str) or not station.strip():
            raise ValueError("El reporte debe indicar una estación")
        self.data = data            # EventData (already validated)
        self.revision = revision
        self.station = station      # name of the station that sends it
