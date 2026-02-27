from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

import pandas as pd

from foa_extract.models import FundingOpportunity

logger = logging.getLogger(__name__)


def ensure_output_dir(out_dir: str | Path) -> Path:
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_json(opportunity: FundingOpportunity, out_dir: str | Path) -> Path:
    out_path = ensure_output_dir(out_dir) / "foa.json"
    data = opportunity.model_dump()

    fd, tmp_path = tempfile.mkstemp(dir=str(out_dir), suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, str(out_path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    logger.info("JSON exported to %s", out_path)
    return out_path


def export_csv(opportunity: FundingOpportunity, out_dir: str | Path) -> Path:
    out_path = ensure_output_dir(out_dir) / "foa.csv"
    export_dict = opportunity.to_export_dict()

    df = pd.DataFrame([export_dict])

    column_order = [
        "foa_id", "title", "agency", "open_date", "close_date",
        "eligibility", "description", "source_url", "tags",
        "award_ceiling", "award_floor", "expected_awards",
    ]
    existing_columns = [c for c in column_order if c in df.columns]
    extra_columns = [c for c in df.columns if c not in column_order]
    df = df[existing_columns + extra_columns]

    fd, tmp_path = tempfile.mkstemp(dir=str(out_dir), suffix=".csv.tmp")
    try:
        os.close(fd)
        df.to_csv(tmp_path, index=False, encoding="utf-8")
        os.replace(tmp_path, str(out_path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    logger.info("CSV exported to %s", out_path)
    return out_path


def export_all(
    opportunity: FundingOpportunity,
    out_dir: str | Path,
    formats: list[str] | None = None,
) -> dict[str, Path]:
    formats = formats or ["json", "csv"]
    results = {}

    if "json" in formats:
        results["json"] = export_json(opportunity, out_dir)

    if "csv" in formats:
        results["csv"] = export_csv(opportunity, out_dir)

    return results
