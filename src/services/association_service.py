from ..models.event_record import DELETED


class AssociationService:
    # Keeps, for each event, the reference event it is associated with

    def __init__(self, registry, w10=480, r10=400):
        self.registry = registry
        self.w10 = w10          # W in tenths of an hour (48.0 h -> 480)
        self.r10 = r10          # R in tenths of km      (40.0 km -> 400)
        self.references = {}    # {event_id: reference_event_id}

    # ---------- the rule of section 7 ----------

    def distance2(self, a, b):
        # Squared distance between epicenters (tenths of km, no square root)
        dx = a.data.x10 - b.data.x10
        dy = a.data.y10 - b.data.y10
        return dx * dx + dy * dy

    def is_candidate(self, a, b):
        # True if event a can be the reference of event b
        if a.state == DELETED:
            return False
        if a.data.event_id == b.data.event_id:
            return False
        if a.data.magnitude10 <= b.data.magnitude10:        # needs a GREATER magnitude
            return False
        elapsed = b.data.time_epoch - a.data.time_epoch      # seconds
        if elapsed <= 0:                                     # a must be STRICTLY before b
            return False
        if elapsed > self.w10 * 360:                         # tenths of hour -> seconds
            return False
        return self.distance2(a, b) <= self.r10 * self.r10   # border included

    def candidates_of(self, b):
        # All the events that can be the reference of b
        result = []
        for a in self.registry.records.values():
            if self.is_candidate(a, b):
                result.append(a)
        return result

    # ---------- the deterministic policy ----------

    def rank(self, a, b):
        # Smaller tuple wins: higher magnitude, then closer, then lower id
        return (-a.data.magnitude10, self.distance2(a, b), a.data.event_id)

    def choose(self, candidates, b):
        best = candidates[0]
        for a in candidates:
            if self.rank(a, b) < self.rank(best, b):
                best = a
        return best

    # ---------- keeping the associations up to date ----------

    def recompute(self, b):
        # Recompute the reference of event b from scratch
        b_id = b.data.event_id
        if b.state == DELETED:
            self.references.pop(b_id, None)
            return
        candidates = self.candidates_of(b)
        if len(candidates) == 0:
            self.references.pop(b_id, None)       # no candidates: no association
        else:
            self.references[b_id] = self.choose(candidates, b).data.event_id

    def on_event_changed(self, x_id):
        # Call after a create, a correction or a reactivation of event x
        x = self.registry.get(x_id)
        for b in self.registry.records.values():
            if b.state == DELETED:
                continue
            b_id = b.data.event_id
            if b_id == x_id:
                self.recompute(b)                          # x itself
            elif self.references.get(b_id) == x_id:
                self.recompute(b)                          # x was its reference
            elif self.is_candidate(x, b):
                self.recompute(b)                          # x is a candidate now

    def on_event_deleted(self, x_id):
        # Call AFTER marking event x as DELETED 
        self.references.pop(x_id, None)
        for b in self.registry.records.values():
            if b.state != DELETED and self.references.get(b.data.event_id) == x_id:
                self.recompute(b)

    def set_parameters(self, w10, r10):
        # Change W and R (both must be positive) and update every association
        if w10 <= 0 or r10 <= 0:
            raise ValueError("W and R must be positive")
        self.w10 = w10
        self.r10 = r10
        for b in self.registry.records.values():
            self.recompute(b)

    def reference_of(self, event_id):
        # The id of the chosen reference, or None
        return self.references.get(event_id)

    def used_by(self, event_id):
        # Ids of the events that use this event as their reference
        result = []
        for b_id, ref_id in self.references.items():
            if ref_id == event_id:
                result.append(b_id)
        return sorted(result)