"""Veri setinin yapısını ve temel kalite sorunlarını inceler."""

import pandas as pd

from ._utils import hashable_cells, select_columns


def dataset_overview(df: pd.DataFrame) -> pd.DataFrame:
    """Satır, sütun, eksik hücre, tekrar ve bellek özetini üretir."""
    df = hashable_cells(df)
    values = {
        "rows": len(df),
        "columns": len(df.columns),
        "missing_cells": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
        "memory_mb": round(df.memory_usage(deep=True).sum() / 1024**2, 3),
    }
    return pd.DataFrame(values.items(), columns=["metric", "value"])


def column_table(df: pd.DataFrame, columns=None) -> pd.DataFrame:
    """Sütun adlarını, tiplerini, eksik ve benzersiz değer sayılarını listeler."""
    data = select_columns(df, columns)
    return pd.DataFrame(
        {
            "column": data.columns,
            "dtype": data.dtypes.astype(str).to_numpy(),
            "non_null": data.notna().sum().to_numpy(),
            "null": data.isna().sum().to_numpy(),
            "null_percent": (data.isna().mean().mul(100).round(2)).to_numpy(),
            "unique": data.nunique(dropna=True).to_numpy(),
        }
    )


def quality_report(df: pd.DataFrame, missing_threshold: float = 30) -> pd.DataFrame:
    """Yüksek eksik oranı, sabitlik, karışık tip ve olası anahtarları bulur."""
    df = hashable_cells(df)
    issues = []
    for column in df.columns:
        series, non_null = df[column], int(df[column].notna().sum())
        unique, missing = int(series.nunique(dropna=True)), float(series.isna().mean() * 100)
        if non_null == 0:
            issues.append((column, "all_null", "Sütunun tamamı boş"))
        elif missing >= missing_threshold:
            issues.append((column, "high_missing", f"%{missing:.2f} eksik"))
        if non_null and unique <= 1:
            issues.append((column, "constant", "Tek bir benzersiz değer var"))
        if non_null > 1 and unique == non_null:
            issues.append((column, "possible_key", "Boş olmayan değerlerin tümü benzersiz"))
        if series.dtype == "object" and series.dropna().map(type).nunique() > 1:
            issues.append((column, "mixed_types", "Birden fazla Python veri tipi var"))
    if df.duplicated().any():
        issues.append(("<dataset>", "duplicate_rows", f"{df.duplicated().sum()} tekrar satır"))
    return pd.DataFrame(issues, columns=["column", "issue", "detail"])
