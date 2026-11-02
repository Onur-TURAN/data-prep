"""Seçilen sütunlar için tablo tabanlı keşifsel veri analizi üretir."""

import pandas as pd

from ._utils import select_columns
from .inspect import column_table, dataset_overview, quality_report


def numeric_summary(df: pd.DataFrame, columns=None) -> pd.DataFrame:
    """Sayısal sütunların dağılımını ve IQR aykırı değer sayısını özetler."""
    numeric = select_columns(df, columns).select_dtypes(include="number")
    if numeric.empty:
        return pd.DataFrame(columns=["column", "count", "mean", "std", "min", "25%", "50%", "75%", "max", "missing", "iqr_outliers"])
    summary = numeric.describe().T
    q1, q3 = numeric.quantile(0.25), numeric.quantile(0.75)
    summary["missing"] = numeric.isna().sum()
    summary["iqr_outliers"] = ((numeric.lt(q1 - 1.5 * (q3 - q1))) | (numeric.gt(q3 + 1.5 * (q3 - q1)))).sum()
    return summary.reset_index(names="column").round(4)


def categorical_summary(df: pd.DataFrame, columns=None) -> pd.DataFrame:
    """Sayısal olmayan sütunların benzersizlik, tepe değer ve eksik özetini verir."""
    categorical = select_columns(df, columns).select_dtypes(exclude="number")
    rows = []
    for column in categorical:
        counts = categorical[column].value_counts(dropna=True)
        counts = counts[counts > 0]
        rows.append(
            {
                "column": column,
                "count": int(categorical[column].notna().sum()),
                "unique": int(categorical[column].nunique(dropna=True)),
                "top": str(counts.index[0]) if len(counts) else None,
                "top_count": int(counts.iloc[0]) if len(counts) else 0,
                "missing": int(categorical[column].isna().sum()),
                "missing_percent": round(categorical[column].isna().mean() * 100, 2),
            }
        )
    return pd.DataFrame(rows, columns=["column", "count", "unique", "top", "top_count", "missing", "missing_percent"])


def correlation_table(df: pd.DataFrame, columns=None) -> pd.DataFrame:
    """Sayısal sütunlar için Pearson korelasyon matrisi döndürür."""
    numeric = select_columns(df, columns).select_dtypes(include="number")
    if numeric.empty:
        return pd.DataFrame()
    label = "column" if "column" not in numeric.columns else "column_"
    return numeric.corr().rename_axis(label).reset_index().round(4)


def frequency_tables(df: pd.DataFrame, columns=None, top_n: int = 10) -> dict[str, pd.DataFrame]:
    """Her seçili sütunun en sık görülen değerlerini ayrı tablo yapar."""
    data = select_columns(df, columns)
    tables = {}
    for column in data:
        table = data[column].value_counts(dropna=False).head(top_n).rename_axis("value").reset_index(name="count")
        table["percent"] = table["count"].div(len(data)).mul(100).round(2) if len(data) else 0
        tables[f"frequency_{column}"] = table
    return tables


def analyze_columns(df: pd.DataFrame, columns=None, top_n: int = 10) -> dict[str, pd.DataFrame]:
    """Tüm temel analiz tablolarını tek sözlükte toplar."""
    data = select_columns(df, columns)
    frequency_columns = list(data.columns) if columns is not None else list(data.select_dtypes(exclude="number").columns)
    return {
        "overview": dataset_overview(data),
        "columns": column_table(data),
        "quality": quality_report(data),
        "numeric_summary": numeric_summary(data),
        "categorical_summary": categorical_summary(data),
        "correlation": correlation_table(data),
        **frequency_tables(data, frequency_columns, top_n),
    }
