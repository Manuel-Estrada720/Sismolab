class EventData:
    # Physical data of an earthquake. Decimals are stored as tenths (5.2 -> 52)

    def __init__(self, event_id, magnitude10, depth10, x10, y10, time_epoch):
        # Validate before saving anything. Messages are shown in the GUI (Spanish)
        for value in (event_id, magnitude10, depth10, x10, y10, time_epoch):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("Los datos del evento deben ser números enteros en décimas")
        if not 1 <= event_id <= 999999:
            raise ValueError("El identificador debe estar entre 1 y 999999")
        if not -20 <= magnitude10 <= 100:
            raise ValueError("La magnitud debe estar entre -2.0 y 10.0")
        if not 0 <= depth10 <= 7000:
            raise ValueError("La profundidad debe estar entre 0.0 y 700.0 km")
        if not (0 <= x10 <= 10000 and 0 <= y10 <= 10000):
            raise ValueError("Las coordenadas deben estar entre 0.0 y 1000.0 km")
        if time_epoch < 0:
            raise ValueError("La fecha de ocurrencia no es válida")

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