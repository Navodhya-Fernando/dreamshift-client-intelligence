from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values, find_dotenv


def _dotenv_data() -> dict[str, str]:
    path = find_dotenv(usecwd=True)
    if not path:
        local = Path(__file__).resolve().parents[1] / ".env"
        path = str(local) if local.exists() else ""
    if not path:
        return {}
    return {
        str(key): str(value)
        for key, value in dotenv_values(path).items()
        if key and value is not None
    }


def _value(name: str, data: dict[str, str]) -> str | None:
    value = os.getenv(name)
    if value is None:
        value = data.get(name)
    if value is None:
        return None
    cleaned = str(value).strip().strip('"').strip("'")
    return cleaned or None


@dataclass(frozen=True)
class Settings:
    airtable_token: str | None
    airtable_pat: str | None
    airtable_base_id: str
    airtable_table_id: str

    @property
    def effective_airtable_token(self) -> str | None:
        return self.airtable_token or self.airtable_pat


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data = _dotenv_data()
    return Settings(
        airtable_token=_value("AIRTABLE_TOKEN", data),
        airtable_pat=_value("AIRTABLE_PAT", data),
        airtable_base_id=_value("AIRTABLE_BASE_ID", data) or "",
        airtable_table_id=_value("AIRTABLE_TABLE_ID", data) or "",
    )
