"""Dynamic metrics endpoint — computed entirely from real DB data."""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import storage

router = APIRouter()


def _date_label(d: date) -> str:
    return d.strftime("%b") + " " + str(d.day)


@router.get("/api/metrics")
async def get_metrics() -> JSONResponse:
    stats = await storage.get_case_stats()

    case_count       = stats["case_count"]
    total_fields     = stats["total_fields"]
    total_corrections = stats["total_corrections"]
    conf_values      = stats["confidence_values"]
    field_stats      = stats["field_stats"]
    case_dates       = stats["case_dates"]

    # Overall accuracy
    if total_fields > 0:
        accuracy = round((total_fields - total_corrections) / total_fields, 4)
    else:
        accuracy = None

    # Avg confidence
    avg_conf = round(statistics.mean(conf_values), 4) if conf_values else None

    # Field-level accuracy (only fields with at least 1 occurrence)
    field_accuracy_list = []
    for fname, fs in field_stats.items():
        if fs["total"] == 0:
            continue
        acc = round((fs["total"] - fs["corrections"]) / fs["total"], 4)
        field_accuracy_list.append({
            "field": fname.replace("_", " ").title(),
            "accuracy": acc,
            "count": fs["total"],
        })
    field_accuracy_list.sort(key=lambda x: x["accuracy"], reverse=True)

    # Confidence distribution
    if conf_values:
        n = len(conf_values)
        conf_dist = {
            "green": round(sum(1 for c in conf_values if c >= 0.85) / n * 100),
            "amber": round(sum(1 for c in conf_values if 0.70 <= c < 0.85) / n * 100),
            "red":   round(sum(1 for c in conf_values if c < 0.70) / n * 100),
        }
    else:
        conf_dist = {"green": 0, "amber": 0, "red": 0}

    # Daily throughput — last 14 days from real case dates
    real_by_date = Counter(case_dates)
    today = date.today()
    daily = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        daily.append({"date": _date_label(d), "count": real_by_date.get(str(d), 0)})

    return JSONResponse({
        "overall_accuracy":        accuracy,
        "avg_confidence":          avg_conf,
        "avg_latency_ms":          None,
        "cost_per_doc_usd":        None,
        "total_cases_processed":   case_count,
        "corrections_this_month":  total_corrections,
        "field_accuracy":          field_accuracy_list,
        "confidence_distribution": conf_dist,
        "daily_throughput":        daily,
    })
