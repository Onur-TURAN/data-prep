"""Büyük CSV dosyalarını sınırlı bellekle örnekler ve özetler."""

import math
import numbers
from pathlib import Path

import pandas as pd

from .io import CSV_ENCODINGS, _sniff_sep


def sample_dataset(df: pd.DataFrame, n: int | None = None, frac: float | None = None, seed: int = 42) -> pd.DataFrame:
    """Satır sayısı veya oran ile tekrarlanabilir bir örnek döndürür."""
    if (n is None) == (frac is None):
        raise ValueError("n veya frac değerlerinden yalnızca biri verilmeli")
    if n is not None:
        if isinstance(n, bool) or not isinstance(n, numbers.Integral) or n < 0:
            raise ValueError("n negatif olmayan bir tamsayı olmalı")
        return df if n >= len(df) else df.sample(n=n, random_state=seed)
    if isinstance(frac, bool) or not isinstance(frac, numbers.Real) or not math.isfinite(frac) or not 0 <= frac <= 1:
        raise ValueError("frac, 0 ile 1 arasında bir sayı olmalı")
    return df.sample(frac=frac, random_state=seed)


def _update_column(state: dict, series: pd.Series) -> None:
    """Bir parçanın sayım ve sayısal toplamlarını sütun birikimine ekler."""
    values = series.dropna()
    state["non_null"] += len(values)
    state["null"] += len(series) - len(values)
    if values.empty:
        return
    numeric = pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)
    state["numeric"] = state["numeric"] and numeric
    if not state["numeric"]:
        return
    low, high = values.min(), values.max()
    low = low.item() if hasattr(low, "item") else low
    high = high.item() if hasattr(high, "item") else high
    state["min"] = low if state["min"] is None else min(state["min"], low)
    state["max"] = high if state["max"] is None else max(state["max"], high)
    # Python tamsayıları, parça toplamında int64 taşmasını önler.
    state["sum"] += sum(values.tolist())


def _profile_reader(reader) -> dict[str, pd.DataFrame]:
    """Parçaları saklamadan sütun başına sabit boyutlu birikimleri tablolar."""
    states, rows, chunks = {}, 0, 0
    for chunk in reader:
        rows += len(chunk)
        chunks += bool(len(chunk))
        for column in chunk:
            state = states.setdefault(column, {"non_null": 0, "null": 0, "numeric": True, "min": None, "max": None, "sum": 0})
            _update_column(state, chunk[column])
    columns = []
    for column, state in states.items():
        numeric = state["numeric"] and state["non_null"] > 0
        columns.append({
            "column": column, "non_null": state["non_null"], "null": state["null"],
            "null_percent": state["null"] * 100 / rows if rows else 0.0,
            "min": state["min"] if numeric else None, "max": state["max"] if numeric else None,
            "mean": state["sum"] / state["non_null"] if numeric else None,
        })
    overview = {"rows": rows, "columns": len(states), "chunks": chunks, "missing_cells": sum(s["null"] for s in states.values())}
    table = pd.DataFrame(columns, columns=["column", "non_null", "null", "null_percent", "min", "max", "mean"])
    # Sayısal olmayan sonuçlar, pandas'ın NaN dönüşümü yerine gerçekten None kalsın.
    for name in ("min", "max", "mean"):
        table[name] = pd.Series([row[name] for row in columns], dtype=object)
    return {"overview": pd.DataFrame(overview.items(), columns=["metric", "value"]), "columns": table}


def profile_csv_in_chunks(path: str | Path, chunksize: int = 100_000, **read_csv_kwargs) -> dict[str, pd.DataFrame]:
    """CSV dosyasının sayım ve sayısal istatistiklerini parça parça hesaplar."""
    if isinstance(chunksize, bool) or not isinstance(chunksize, numbers.Integral) or chunksize <= 0:
        raise ValueError("chunksize pozitif bir tamsayı olmalı")
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Veri seti bulunamadı: {path}")
    if "iterator" in read_csv_kwargs:
        raise ValueError("iterator yerine chunksize kullanılmalı")
    sep = read_csv_kwargs.pop("sep", None) or _sniff_sep(path)
    encodings = [read_csv_kwargs.pop("encoding")] if "encoding" in read_csv_kwargs else CSV_ENCODINGS
    for encoding in encodings:
        try:
            with pd.read_csv(path, chunksize=chunksize, sep=sep, encoding=encoding, **read_csv_kwargs) as reader:
                return _profile_reader(reader)
        except UnicodeDecodeError as exc:
            error = exc
    raise error
