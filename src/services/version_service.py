"""Section 13: named versions saved as JSON files under data/versions/."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..persistence.exporter import export_to_file

DEFAULT_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "versions"
NAME_PATTERN = re.compile(r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ _.-]{1,60}$")


class VersionService:

    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else DEFAULT_DIRECTORY

    @staticmethod
    def _check_name(name):
        if not isinstance(name, str) or not NAME_PATTERN.match(name.strip()):
            raise ValueError(
                "El nombre de la versión debe tener entre 1 y 60 caracteres "
                "(letras, números, espacios, punto, guion o guion bajo)"
            )
        return name.strip()

    def _path(self, name):
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._") or "version"
        return self.directory / (slug + ".json")

    def save(self, name, scenario_document):
        name = self._check_name(name)
        document = {
            "version_name": name,
            "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scenario": scenario_document,
        }
        path = self._path(name)
        export_to_file(path, document)
        return path.name

    def list(self):
        versions = []
        if not self.directory.exists():
            return versions
        for path in sorted(self.directory.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as stream:
                    document = json.load(stream)
                versions.append({
                    "name": document["version_name"],
                    "saved_at": document.get("saved_at"),
                    "file": path.name,
                    "events": len(document["scenario"].get("events", [])),
                })
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                continue        # not a version file: ignore it
        versions.sort(key=lambda item: item["saved_at"] or "", reverse=True)
        return versions

    def load(self, name):
        name = self._check_name(name)
        path = self._path(name)
        if not path.exists():
            raise ValueError("No existe una versión llamada " + repr(name))
        with open(path, "r", encoding="utf-8") as stream:
            document = json.load(stream)
        return document["scenario"]
