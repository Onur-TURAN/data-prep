"""Sütun ve veri seti kurallarını tablo halinde doğrular."""

import datetime
import json
import math
import numbers
import re
from pathlib import Path

import numpy as np
import pandas as pd

from ._utils import hashable_cells

COLUMN_RULES = {"required", "dtype", "min", "max", "allowed", "pattern", "unique", "max_missing_percent"}
DATASET_RULES = {"min_rows", "unique_key", "no_duplicate_rows"}
REPORT_COLUMNS = ["column", "rule", "expected", "failed_rows", "sample_values", "passed"]


def _check_keys(value: dict, allowed: set[str], location: str) -> None:
    """Kural bölümlerinin sözlük olduğunu ve yalnızca bilinen anahtarları içerdiğini denetler."""
    if not isinstance(value, dict):
        raise ValueError(f"{location} bir sözlük olmalı")
    unknown = value.keys() - allowed
    if unknown:
        raise ValueError(f"{location} içinde bilinmeyen kural: {', '.join(map(str, unknown))}")


def _finite_number(value: object) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, (bool, np.bool_)) and math.isfinite(value)


def _check_column_rules(rules: dict) -> None:
    """Sütun kurallarının değerlerini ve düzenli ifadelerini denetler."""
    _check_keys(rules, COLUMN_RULES, "Sütun kuralları")
    for key, value in rules.items():
        valid = True
        if key in {"required", "unique"}:
            valid = isinstance(value, bool)
        elif key == "dtype":
            valid = isinstance(value, str) and value in {"number", "string", "datetime", "bool"}
        elif key == "allowed":
            valid = isinstance(value, list)
        elif key == "max_missing_percent":
            valid = _finite_number(value) and 0 <= value <= 100
        elif key == "pattern":
            valid = isinstance(value, str)
            if valid:
                try:
                    re.compile(value)
                except re.error as exc:
                    raise ValueError(f"Geçersiz düzenli ifade: {value}") from exc
        elif key in {"min", "max"}:
            valid = _finite_number(value)
            if isinstance(value, str):
                try:
                    datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
                    valid = True
                except ValueError:
                    valid = False
        if not valid:
            raise ValueError(f"Geçersiz kural değeri: {key} = {value}")
    if "min" in rules and "max" in rules:
        low, high = rules["min"], rules["max"]
        try:
            ordered = pd.Timestamp(low) <= pd.Timestamp(high) if isinstance(low, str) and isinstance(high, str) else low <= high
        except TypeError:
            ordered = False
        if not ordered:
            raise ValueError("min ve max aynı türde olmalı; min, max değerini aşmamalı")


def _check_rules(rules: dict) -> None:
    """Kural dosyasının tüm bölümlerini doğrular."""
    _check_keys(rules, {"columns", "dataset"}, "Kurallar")
    columns, dataset = rules.get("columns", {}), rules.get("dataset", {})
    if not isinstance(columns, dict) or not all(isinstance(c, str) for c in columns):
        raise ValueError("columns, metin sütun adlarından oluşan bir sözlük olmalı")
    for column_rules in columns.values():
        _check_column_rules(column_rules)
    _check_keys(dataset, DATASET_RULES, "Veri seti kuralları")
    for key, value in dataset.items():
        valid = isinstance(value, bool)
        if key == "min_rows":
            valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
        elif key == "unique_key":
            valid = isinstance(value, list) and bool(value) and all(isinstance(c, str) for c in value)
            valid = valid and len(set(value)) == len(value)
        if not valid:
            raise ValueError(f"Geçersiz veri seti kuralı: {key} = {value}")


def load_rules(path: str | Path) -> dict:
    """UTF-8 JSON kurallarını okur ve geçersiz kuralları reddeder."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Kural dosyası bulunamadı: {path}")
    try:
        rules = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Kural dosyası geçerli UTF-8 JSON olmalı") from exc
    _check_rules(rules)
    return rules


def _dtype_failures(values: pd.Series, dtype: str) -> pd.Series:
    """Boş olmayan hücrelerde istenen gerçek veri tipine uymayanları bulur."""
    checks = {
        "number": lambda v: isinstance(v, numbers.Number) and not isinstance(v, (bool, np.bool_)),
        "string": lambda v: isinstance(v, str),
        "datetime": lambda v: isinstance(v, (datetime.datetime, datetime.date, np.datetime64)),
        "bool": lambda v: isinstance(v, (bool, np.bool_)),
    }
    return ~values.astype(object).map(checks[dtype]).astype(bool)


def _bound_failures(values: pd.Series, bound: object, rule: str) -> pd.Series:
    """Sayıya veya tarihe çevrilemeyen değerleri de sınır ihlali sayar."""
    if isinstance(bound, str):
        converted = pd.to_datetime(values.astype(object), errors="coerce", format="mixed", utc=True)
        bound = pd.to_datetime(bound, utc=True)
    else:
        converted = pd.to_numeric(values.astype(object), errors="coerce")
    comparison = converted.lt(bound) if rule == "min" else converted.gt(bound)
    return converted.isna() | comparison.fillna(False)


def _column_failures(series: pd.Series, rule: str, expected: object) -> pd.Series:
    """Tek bir sütun kuralında başarısız olan hücreleri döndürür."""
    values = series.dropna()
    if rule == "required":
        return series[series.isna()] if expected else series.iloc[:0]
    if rule == "max_missing_percent":
        percent = series.isna().sum() * 100 / len(series) if len(series) else 0
        return series[series.isna()] if percent > expected else series.iloc[:0]
    if rule == "dtype":
        mask = _dtype_failures(values, expected)
    elif rule in {"min", "max"}:
        mask = _bound_failures(values, expected, rule)
    elif rule == "allowed":
        mask = ~values.isin(expected)
    elif rule == "pattern":
        mask = ~values.astype(str).str.fullmatch(expected, na=False)
    else:
        mask = values.duplicated(keep=False) if expected else pd.Series(False, index=values.index)
    return values[mask]


def _result(column: str, rule: str, expected: object, failed: int, samples=()) -> dict:
    return {
        "column": column, "rule": rule, "expected": str(expected), "failed_rows": int(failed),
        "sample_values": ", ".join(str(value) for value in list(samples)[:5]), "passed": failed == 0,
    }


def _dataset_results(df: pd.DataFrame, rules: dict) -> list[dict]:
    """Veri setinin satır sayısını, anahtarını ve tekrarlarını denetler."""
    rows = []
    for rule, expected in rules.items():
        if rule == "min_rows":
            rows.append(_result("<dataset>", rule, expected, max(0, expected - len(df))))
            continue
        if rule == "unique_key" and any(c not in df for c in expected):
            continue
        data = hashable_cells(df[expected] if rule == "unique_key" else df)
        mask = data.duplicated(keep=False) if rule == "unique_key" or expected else pd.Series(False, index=df.index)
        if rule == "unique_key":
            mask |= data.isna().any(axis=1)
        samples = data.loc[mask].head(5).itertuples(index=False, name=None)
        rows.append(_result("<dataset>", rule, expected, int(mask.sum()), samples))
    return rows


def validate(df: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """Her kuralın başarısını, ihlal sayısını ve en çok beş örneğini tablolar."""
    _check_rules(rules)
    rows, missing = [], set()
    for column, column_rules in rules.get("columns", {}).items():
        if column not in df:
            rows.append(_result(column, "exists", True, 1))
            missing.add(column)
            continue
        for rule, expected in column_rules.items():
            failures = _column_failures(df[column], rule, expected)
            rows.append(_result(column, rule, expected, len(failures), failures.head(5)))
    dataset = rules.get("dataset", {})
    for column in dataset.get("unique_key", []):
        if column not in df and column not in missing:
            rows.append(_result(column, "exists", True, 1))
            missing.add(column)
    rows.extend(_dataset_results(df, dataset))
    return pd.DataFrame(rows, columns=REPORT_COLUMNS).astype({"passed": bool})


def validation_passed(report: pd.DataFrame) -> bool:
    """Raporun tüm kuralları başarılıysa True döndürür; boş rapor başarılıdır."""
    return bool(report["passed"].fillna(False).all())
