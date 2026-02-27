from __future__ import annotations

import re
from datetime import date
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


class FundingOpportunity(BaseModel):
    foa_id: str
    title: str
    agency: str = ""
    open_date: Optional[str] = None
    close_date: Optional[str] = None
    eligibility: str = ""
    description: str = ""
    source_url: str = ""
    tags: list[str] = []
    award_ceiling: Optional[str] = None
    award_floor: Optional[str] = None
    expected_awards: Optional[str] = None

    @field_validator("open_date", "close_date", mode="before")
    @classmethod
    def normalize_date(cls, value: str | None) -> str | None:
        if not value or not str(value).strip():
            return None
        return format_date(str(value).strip())

    @field_validator("foa_id", "title", mode="before")
    @classmethod
    def strip_whitespace(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def coerce_empty_strings(self) -> "FundingOpportunity":
        for field_name in ("agency", "eligibility", "description"):
            val = getattr(self, field_name)
            if val is not None and isinstance(val, str) and not val.strip():
                object.__setattr__(self, field_name, "")
        return self

    def to_export_dict(self) -> dict:
        data = self.model_dump()
        data["tags"] = "; ".join(data.get("tags", []))
        return data


_ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def format_date(raw: str) -> str | None:
    raw = raw.strip()
    if not raw:
        return None

    if _ISO_PATTERN.match(raw):
        return raw

    slash_match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if slash_match:
        m, d, y = slash_match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"

    text_match = re.match(
        r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", raw
    )
    if text_match:
        month_str, day_str, year_str = text_match.groups()
        month_num = _MONTH_MAP.get(month_str.lower())
        if month_num:
            return f"{year_str}-{month_num:02d}-{int(day_str):02d}"

    text_match_2 = re.match(
        r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", raw
    )
    if text_match_2:
        day_str, month_str, year_str = text_match_2.groups()
        month_num = _MONTH_MAP.get(month_str.lower())
        if month_num:
            return f"{year_str}-{month_num:02d}-{int(day_str):02d}"

    try:
        from dateutil import parser as dateutil_parser
        parsed = dateutil_parser.parse(raw, fuzzy=True)
        return parsed.strftime("%Y-%m-%d")
    except (ValueError, ImportError):
        return None
