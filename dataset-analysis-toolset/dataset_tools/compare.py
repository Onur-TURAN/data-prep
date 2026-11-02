"""İki veri setinin şema, sütun ve anahtar bazlı satır farklarını karşılaştırır."""

import numbers
from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd

from ._utils import hashable_cells


def compare_schema(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    """Her iki veri setindeki sütun varlığını ve veri tiplerini karşılaştırır."""
    schema = pd.concat(
        [left.dtypes.astype(str).rename("left_dtype"), right.dtypes.astype(str).rename("right_dtype")],
        axis=1,
    ).rename_axis("column").reset_index()
    schema["in_left"], schema["in_right"] = schema["left_dtype"].notna(), schema["right_dtype"].notna()
    schema["dtype_match"] = schema["left_dtype"].eq(schema["right_dtype"])
    return schema


def _pair(item: str | Sequence[str]) -> tuple[str, str]:
    return (item, item) if isinstance(item, str) else (item[0], item[1])


def _typed_value(value) -> tuple[str, str]:
    """20 ile 20.0 aynı sayılsın diye sayıları ortak biçime getirir; '20' metni ayrı kalır."""
    if isinstance(value, (bool, np.bool_)):
        return "bool", str(value)
    if isinstance(value, numbers.Integral):
        return "number", str(int(value))
    if isinstance(value, numbers.Real):
        value = float(value)
        return "number", str(int(value)) if value.is_integer() else repr(value)
    return type(value).__name__, str(value)


def _mean(series: pd.Series) -> float | None:
    mean = series.mean()
    return None if pd.isna(mean) else round(float(mean), 4)


def _payload(series: pd.Series) -> pd.Series:
    """Kategorik sütunları ham değere, tamsayıları outer join'de float'a dönmeyen Int64'e çevirir."""
    if isinstance(series.dtype, pd.CategoricalDtype):
        return series.astype(object)
    if pd.api.types.is_integer_dtype(series) and not pd.api.types.is_extension_array_dtype(series):
        return series.astype("Int64")
    return series


def _typed_value_or_na(value):
    return value if pd.isna(value) else _typed_value(value)[1]


def _typed_values(series: pd.Series) -> set[tuple[str, str]]:
    return set(series.dropna().map(_typed_value))


def compare_columns(left: pd.DataFrame, right: pd.DataFrame, pairs: Iterable[str | Sequence[str]]) -> pd.DataFrame:
    """Seçili sütun çiftlerinin eksik, benzersiz, ortak değer ve ortalama farklarını verir."""
    rows = []
    for left_column, right_column in map(_pair, pairs):
        if left_column not in left or right_column not in right:
            raise KeyError(f"Sütun çifti bulunamadı: {left_column} / {right_column}")
        a, b = hashable_cells(left[[left_column]])[left_column], hashable_cells(right[[right_column]])[right_column]
        a_values, b_values = _typed_values(a), _typed_values(b)
        union, common = a_values | b_values, a_values & b_values
        numeric = pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b)
        rows.append(
            {
                "left_column": left_column,
                "right_column": right_column,
                "left_dtype": str(a.dtype),
                "right_dtype": str(b.dtype),
                "left_rows": len(a),
                "right_rows": len(b),
                "left_null_percent": round(a.isna().mean() * 100, 2),
                "right_null_percent": round(b.isna().mean() * 100, 2),
                "left_unique": int(a.nunique(dropna=True)),
                "right_unique": int(b.nunique(dropna=True)),
                "shared_unique": len(common),
                "left_only_unique": len(a_values - b_values),
                "right_only_unique": len(b_values - a_values),
                "jaccard_percent": round(len(common) / len(union) * 100, 2) if union else 100.0,
                "left_mean": _mean(a) if numeric else None,
                "right_mean": _mean(b) if numeric else None,
                "mean_difference": round(_mean(a) - _mean(b), 4) if numeric and pd.notna(_mean(a)) and pd.notna(_mean(b)) else None,
            }
        )
    return pd.DataFrame(rows)


def compare_rows_by_key(left: pd.DataFrame, right: pd.DataFrame, key: str | Sequence[str], columns: Iterable[str]) -> pd.DataFrame:
    """Tekil (tek ya da çok sütunlu) bir anahtara göre yalnızca eksik veya uyuşmayan satırları döndürür."""
    keys = [key] if isinstance(key, str) else list(key)
    columns = [c for c in columns if c not in keys]
    required = [*keys, *columns]
    missing_left, missing_right = [c for c in required if c not in left], [c for c in required if c not in right]
    if missing_left or missing_right:
        raise KeyError(f"Eksik sütunlar - left: {missing_left}, right: {missing_right}")
    if left.duplicated(keys).any() or right.duplicated(keys).any():
        raise ValueError(f"{keys} anahtarı her iki veri setinde de tekil olmalı")

    a = left[required].apply(_payload).rename(columns={c: f"{c}__left" for c in columns})
    b = right[required].apply(_payload).rename(columns={c: f"{c}__right" for c in columns})
    for k in keys:
        if a[k].dtype != b[k].dtype:
            # Örn. bir dosyada 1, diğerinde "1": merge'ün tip hatası vermemesi için anahtarlar metne çevrilir.
            a[k], b[k] = a[k].map(_typed_value_or_na), b[k].map(_typed_value_or_na)
    if a.duplicated(keys).any() or b.duplicated(keys).any():
        raise ValueError(f"{keys} anahtarı metne çevrildikten sonra tekil değil (örn. 1 ve '1' birlikte var)")
    indicator = "__row_status__"
    merged = a.merge(b, on=keys, how="outer", indicator=indicator)
    mismatch = merged[indicator].ne("both")
    for column in columns:
        x, y = merged[f"{column}__left"], merged[f"{column}__right"]
        # Nullable sütunlarda eq() NA döndürür; NA'yı "farklı" sayıyoruz ki boş→dolu değişimler kaybolmasın.
        same = x.eq(y).fillna(False).astype(bool) | (x.isna() & y.isna())
        merged[f"{column}__match"] = same
        mismatch |= ~same
    merged = merged.rename(columns={indicator: "row_status"}) if "row_status" not in keys else merged
    return merged.loc[mismatch].reset_index(drop=True)
