"""Pfade und Studienkonfiguration (config/study.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
DATA_MANUAL = ROOT / "data" / "manual"
OUTPUT = ROOT / "output"
DB_PATH = DATA_PROCESSED / "afe.sqlite"
CONFIG_FILE = ROOT / "config" / "study.toml"

# Matomo Heatmap & Session Recording: Ereignistypen in log_hsr_event.event_type
EVENT_TYPES = {
    1: "move",
    2: "click",
    3: "scroll",
    4: "resize",
    5: "initial_dom",
    6: "mutation",
    7: "link_hsr",
    8: "page_treemirror",
    9: "form_text",
    10: "form_value",
    11: "stop_recording",
    12: "scroll_element",
    13: "css",
}
MOUSE_EVENTS = (1, 2)  # Ereignisse mit Mauskoordinaten
DEVICE_TYPES = {1: "desktop", 2: "tablet", 3: "smartphone"}


@dataclass
class AoiRule:
    name: str
    url_regex: str
    selector_regex: str
    description: str = ""


@dataclass
class StudyConfig:
    field_start: str = ""
    field_end: str = ""
    timezone: str = "Europe/Zurich"
    variant_start: dict[str, str] = field(default_factory=dict)
    scale_min: int = 1
    scale_max: int = 5
    exclude_visits_file: str = "config/exclude_visits.csv"
    device_types: list[int] = field(default_factory=list)
    require_form: bool = False
    min_total_s: float = 0
    op_url_contains: str = "one-pager"
    form_url_contains: str = "kontakt"
    direction_min_delta: int = 20
    pause_ms: int = 1000
    dwell_cap_ms: int = 3000
    aoi: list[AoiRule] = field(default_factory=list)

    @property
    def exclude_path(self) -> Path:
        return ROOT / self.exclude_visits_file


def load_config(path: Path | None = None) -> StudyConfig:
    raw = tomllib.loads((path or CONFIG_FILE).read_text(encoding="utf-8"))
    s, v, m = raw.get("sample", {}), raw.get("variants", {}), raw.get("metrics", {})
    return StudyConfig(
        field_start=s.get("field_start", ""),
        field_end=s.get("field_end", ""),
        timezone=s.get("timezone", "Europe/Zurich"),
        variant_start=dict(s.get("variant_start", {})),
        scale_min=int(raw.get("questionnaire", {}).get("scale_min", 1)),
        scale_max=int(raw.get("questionnaire", {}).get("scale_max", 5)),
        exclude_visits_file=s.get("exclude_visits_file", "config/exclude_visits.csv"),
        device_types=list(s.get("device_types", [])),
        require_form=bool(s.get("require_form", False)),
        min_total_s=float(s.get("min_total_s", 0)),
        op_url_contains=v.get("op_url_contains", "one-pager"),
        form_url_contains=v.get("form_url_contains", "kontakt"),
        direction_min_delta=int(m.get("direction_min_delta", 20)),
        pause_ms=int(m.get("pause_ms", 1000)),
        dwell_cap_ms=int(m.get("dwell_cap_ms", 3000)),
        aoi=[AoiRule(**a) for a in raw.get("aoi", [])],
    )


def ensure_dirs() -> None:
    for d in (DATA_RAW, DATA_PROCESSED, DATA_MANUAL, OUTPUT):
        d.mkdir(parents=True, exist_ok=True)
