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
    net_liquidation_eur: float = 0.0
    last_update: Optional[datetime] = None
    max_age_hours: int = MAX_AGE_HOURS

    @classmethod
    def load(cls, path: str | Path = PATH_STATE) -> "StateStore":
        p = Path(path)
        if not p.exists():
            return cls()
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(
            net_liquidation_eur=float(data.get("net_liquidation_eur", 0.0)),
            last_update=data.get("last_update"),
            max_age_hours=int(data.get("max_age_hours", MAX_AGE_HOURS)),
        )

    def save(self, path: str | Path = PATH_STATE) -> None:
        data = asdict(self)
        with Path(path).open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)

    def is_outdated(self, max_age: timedelta = timedelta(hours=MAX_AGE_HOURS)) -> bool:
        if self.last_update is None:
            return True
        ret = (datetime.now() - self.last_update) > max_age
        return ret
