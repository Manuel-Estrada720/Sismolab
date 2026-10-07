"""Shared helpers for the tests."""

import tempfile

from src.services.observatory import Observatory

OLD_TIME = "2026-09-01T00:00:00Z"       # more than 72 h before the default clock
RECENT_TIME = "2026-09-07T10:00:00Z"    # 2 h before the default clock (12:00)
STATION = "EST-NORTE"


def new_observatory():
    return Observatory(versions_dir=tempfile.mkdtemp())


def event_form(event_id, magnitude, depth="10", x="950", y="950", time=RECENT_TIME, station=STATION):
    # Default epicenter (950, 950) is inside "Llanura Este", a non populated zone
    return {"id": event_id, "magnitude": magnitude, "depth": depth, "x": x, "y": y,
            "time": time, "station": station}


def report_form(event_id, magnitude, revision, station=STATION, **extra):
    form = event_form(event_id, magnitude, station=station, **extra)
    form["revision"] = revision
    return form


def create(observatory, event_id, magnitude, **extra):
    result = observatory.create_event(event_form(event_id, magnitude, **extra))
    assert result["ok"], result["message"]
    return result


def root_id(observatory):
    return observatory.state.tree.root.getEvent().data.event_id


def inorder_ids(observatory):
    return [node.getEvent().data.event_id for node in observatory.state.tree.inorder()]
