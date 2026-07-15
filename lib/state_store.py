from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent

PATH_STATE = BASE_DIR / 'data' / 'state.yaml'
MAX_AGE_HOURS = 12

@dataclass
class StateStore:
    last_update: Optional[datetime] = None

    @classmethod
    def load(cls, path: str | Path = PATH_STATE) -> "StateStore":
        p = Path(path)
        if not p.exists():
            return cls()
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(
            last_update=data.get("last_update"),
        )

    def save(self, path: str | Path = PATH_STATE) -> None:
        data = asdict(self)
        with Path(path).open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
