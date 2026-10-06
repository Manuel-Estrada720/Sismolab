"""Generate the sample JSON files in data/ (reproducible: fixed random seed).

Run from the project root:
    python -m scripts.generate_samples
"""

import json
import random
from pathlib import Path

from src.services.observatory import Observatory

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "data" / "scenarios"
REPORTS = ROOT / "data" / "reports"
STATIONS = ["EST-NORTE", "EST-SUR", "EST-ESTE", "EST-OESTE", "EST-CENTRO"]


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("written", path.relative_to(ROOT))


def random_events(count, seed, first_id=1, ascending=False):
    """Simple events inside the plane. Times go before the default clock."""
    rng = random.Random(seed)
    events = []
    for index in range(count):
        magnitude = 2.0 + index * 0.1 if ascending else rng.randint(-5, 85) / 10
        day = rng.randint(1, 7)
        hour = rng.randint(0, 11) if day == 7 else rng.randint(0, 23)
        events.append({
            "id": first_id + index,
            "magnitude": round(magnitude, 1),
            "depth": rng.randint(0, 1200) / 10,
            "x": rng.randint(0, 10000) / 10,
            "y": rng.randint(0, 10000) / 10,
            "time": "2026-09-%02dT%02d:%02d:00Z" % (day, hour, rng.randint(0, 59)),
            "station": STATIONS[index % len(STATIONS)],
        })
    return events


def must(result):
    assert result["ok"], result["message"]
    return result


def normal_scenario():
    """About 30 events: active, reviewed, archived and deleted, with a queue."""
    obs = Observatory()
    for event in random_events(30, seed=11, first_id=100):
        must(obs.create_event(event))
    for event_id in (101, 105, 110):
        must(obs.mark_reviewed(event_id))
    must(obs.delete_event(120))
    must(obs.correct_event(103, {"magnitude": "6.3", "depth": "12", "station": "EST-SUR"}))
    preview = obs.archive_preview()
    if preview["ok"]:
        must(obs.archive_apply(preview["details"]["ids"]))
    must(obs.enqueue_reports([
        {"id": 200, "magnitude": "4.7", "depth": "20", "x": "550", "y": "420",
         "time": "2026-09-07T11:00:00Z", "station": "EST-ESTE", "revision": 1},
        {"id": 103, "magnitude": "6.3", "depth": "12", "x": obs.get_event(103)["details"]["x"],
         "y": obs.get_event(103)["details"]["y"], "time": obs.get_event(103)["details"]["time"],
         "station": "EST-OESTE", "revision": 2},
    ]))
    return obs.export()


def stress_scenario():
    """Built in stress mode with ascending keys: an ordered but unbalanced tree."""
    obs = Observatory()
    must(obs.create_event({"id": 50, "magnitude": "3.5", "depth": "40", "x": "200", "y": "200",
                           "time": "2026-09-05T08:00:00Z", "station": "EST-NORTE"}))
    must(obs.enter_stress())
    for event in random_events(29, seed=5, first_id=1, ascending=True):
        must(obs.create_event(event))
    return obs.export()


def invalid_topology(document):
    """Break a valid scenario: global order (children swapped) and a stored height."""
    broken = json.loads(json.dumps(document))
    nodes = broken["tree"]["nodes"]
    root = next(node for node in nodes if node["id"] == broken["tree"]["root"])
    left = next(node for node in nodes if node["id"] == root["left"])
    # Swap the root's children: global order is violated
    root["left"], root["right"] = root["right"], root["left"]
    left["height"] += 3
    return broken


def burst_for_normal(document):
    """Reports with every possible decision, for escenario_normal.json."""
    events = {event["id"]: event for event in document["events"]}
    active = [e for e in document["events"] if e["state"] == "ACTIVE"]
    deleted = [e for e in document["events"] if e["state"] == "DELETED"]
    archived = [e for e in document["events"] if e["state"] == "ARCHIVED"]
    first, second = active[0], active[1]

    def report(event, revision, station, **changes):
        data = {name: event[name] for name in ("id", "magnitude", "depth", "x", "y", "time")}
        data.update(changes)
        data["revision"] = revision
        data["station"] = station
        return data

    other = [s for s in STATIONS if s not in first["stations"]][0]
    reports = [
        report({"id": 300, "magnitude": 5.1, "depth": 25.0, "x": 520.0, "y": 450.0,
                "time": "2026-09-07T09:30:00Z"}, 1, "EST-CENTRO"),                    # new
        report(first, first["revision"], other),                                    # confirmation
        report(first, first["revision"], other),                                    # repeated confirmation
        report(second, second["revision"], "EST-SUR", magnitude=1.0),                # conflict
        report(second, second["revision"] + 1, "EST-NORTE", magnitude=6.6),          # correction, key changes
        report(second, second["revision"], "EST-ESTE"),                              # old (after correction)
        report({"id": 301, "magnitude": 3.2, "depth": 5.0, "x": 10.0, "y": 10.0,
                "time": "2026-09-07T11:59:00Z"}, 4, "EST-OESTE"),                    # new with revision 4
    ]
    if deleted:
        reports.append(report(deleted[0], deleted[0]["revision"] + 1, "EST-SUR"))    # rejected
    if archived:
        reports.append(report(archived[0], archived[0]["revision"] + 1, "EST-NORTE",
                              magnitude=4.6))                                         # reactivation
    return {"description": "Ráfaga para escenario_normal.json con altas, confirmaciones, "
                           "conflicto, corrección con cambio de clave, reporte antiguo, "
                           "eliminado rechazado y reactivación de un archivado",
            "reports": reports}


def main():
    normal = normal_scenario()
    write(SCENARIOS / "escenario_normal.json", normal)
    stress = stress_scenario()
    write(SCENARIOS / "escenario_estres.json", stress)
    write(SCENARIOS / "invalido_topologia.json", invalid_topology(normal))

    write(SCENARIOS / "insercion_5.json", {"events": random_events(5, seed=1)})
    write(SCENARIOS / "insercion_30.json", {"events": random_events(30, seed=2)})
    write(SCENARIOS / "insercion_200.json", {"events": random_events(200, seed=3)})
    write(SCENARIOS / "insercion_ascendente.json",
          {"events": random_events(31, seed=4, ascending=True)})
    duplicated = random_events(6, seed=6)
    duplicated[4]["id"] = duplicated[1]["id"]
    duplicated[2]["magnitude"] = 12.5
    write(SCENARIOS / "invalido_insercion.json", {"events": duplicated})

    write(REPORTS / "rafaga_escenario_normal.json", burst_for_normal(normal))
    ascending = []
    for index in range(200):
        # Magnitudes 0.0..4.4 with a far, non populated epicenter: all priority 1,
        # so the keys arrive in ascending order and a stress tree degenerates
        ascending.append({"id": 1000 + index, "magnitude": round((index % 45) / 10, 1),
                          "depth": 50.0, "x": 950.0, "y": 950.0 - index * 0.5,
                          "time": "2026-09-0%dT%02d:00:00Z" % (1 + index // 45, index % 24),
                          "revision": 1, "station": STATIONS[index % len(STATIONS)]})
    ascending.sort(key=lambda r: (r["magnitude"], r["id"]))
    write(REPORTS / "rafaga_200_estres.json", {
        "description": "200 altas con claves ascendentes: en modo estrés el árbol se degrada",
        "reports": ascending,
    })
    write(REPORTS / "rafaga_altas.json", {
        "description": "Ráfaga de altas desde las cinco estaciones (escenario vacío)",
        "reports": [dict(event, revision=1) for event in random_events(10, seed=9, first_id=500)],
    })


if __name__ == "__main__":
    main()
