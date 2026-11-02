"""Veri setini temizleyen küçük adımlar ve bunları sırayla uygulayan bir boru hattı."""

import re
import unicodedata
from collections.abc import Iterable

import pandas as pd

from ._utils import select_columns

TURKISH_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
TRUE_WORDS = {"true", "yes", "evet", "e", "y", "1"}
FALSE_WORDS = {"false", "no", "hayir", "hayır", "h", "n", "0"}
FILL_STRATEGIES = ("mean", "median", "mode", "drop")


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Sütun adlarını küçük harfli, Türkçe karaktersiz snake_case yapar; çakışmalara _2 ekler."""
    names, used = [], set()
    for column in df.columns:
        text = unicodedata.normalize("NFKD", str(column).translate(TURKISH_ASCII)).encode("ascii", "ignore").decode()
        base = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower() or "column"
        name, number = base, 2
        while name in used:
            name, number = f"{base}_{number}", number + 1
        names.append(name)
        used.add(name)
    return df.set_axis(names, axis=1)


def strip_whitespace(df: pd.DataFrame, columns: Iterable[str] | None = None) -> pd.DataFrame:
    """Metin hücrelerindeki baş/son boşlukları siler; boş kalan metinleri eksik değer yapar."""
    data = select_columns(df, columns)
    text_columns = [c for c in data.columns if pd.api.types.is_object_dtype(data[c]) or pd.api.types.is_string_dtype(data[c])]
    stripped = {c: df[c].map(lambda v: (v.strip() or pd.NA) if isinstance(v, str) else v) for c in text_columns}
    return df.assign(**stripped)


def drop_empty(df: pd.DataFrame) -> pd.DataFrame:
    """Tamamen boş satır ve sütunları kaldırır."""
    return df.dropna(axis=1, how="all").dropna(axis=0, how="all")


def drop_duplicate_rows(df: pd.DataFrame, subset: Iterable[str] | None = None) -> pd.DataFrame:
    """Tekrar eden satırların ilkini tutup diğerlerini siler."""
    subset = list(subset) if subset is not None else None
    if subset:
        select_columns(df, subset)
    return df.drop_duplicates(subset=subset).reset_index(drop=True)


def _convert_series(series: pd.Series) -> pd.Series:
    values = series.dropna()
    if values.empty or not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
        return series
    text = values.astype(str).str.strip()
    lowered = set(text.str.lower())
    if lowered <= TRUE_WORDS | FALSE_WORDS and not lowered <= {"0", "1"}:
        return series.map(lambda v: v if pd.isna(v) else str(v).strip().lower() in TRUE_WORDS).astype("boolean")
    for candidate in (text, text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)):
        numbers = pd.to_numeric(candidate, errors="coerce")
        if numbers.notna().all():
            converted = pd.Series(pd.NA, index=series.index, dtype="Float64")
            converted[values.index] = numbers
            return converted.astype("Int64") if (converted.dropna() % 1 == 0).all() else converted
    if text.str.contains(r"\d{1,4}[-./]\d{1,2}[-./]\d{1,4}").all():
        # 2024-04-01 ISO olarak, 01.04.2024 Türkçe gün.ay.yıl olarak okunur.
        iso = text.str.match(r"^\d{4}[-./]")
        dates = pd.concat(
            [
                pd.to_datetime(text[iso].str.replace(r"[./]", "-", regex=True), errors="coerce", format="mixed"),
                pd.to_datetime(text[~iso], errors="coerce", format="mixed", dayfirst=True),
            ]
        )
        if dates.notna().all():
            return dates.reindex(series.index)
    return series


def convert_types(df: pd.DataFrame, columns: Iterable[str] | None = None) -> pd.DataFrame:
    """Metin olarak okunmuş sayı (1.234,5 dahil), tarih ve evet/hayır sütunlarını gerçek tipe çevirir."""
    data = select_columns(df, columns)
    return df.assign(**{c: _convert_series(df[c]) for c in data.columns})


def fill_missing(df: pd.DataFrame, strategy: str | object = "median", columns: Iterable[str] | None = None) -> pd.DataFrame:
    """Eksik değerleri mean/median/mode ile doldurur, 'drop' ile satırı siler ya da verilen sabiti yazar."""
    data = select_columns(df, columns)
    if strategy == "drop":
        return df.dropna(subset=list(data.columns)).reset_index(drop=True)
    filled = {}
    for column in data.columns:
        series = df[column]
        if strategy in ("mean", "median"):
            if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
                continue
            value = getattr(series, strategy)()
            if pd.api.types.is_integer_dtype(series) and pd.notna(value) and value % 1:
                series = series.astype("Float64")
        elif strategy == "mode":
            modes = series.mode(dropna=True)
            value = modes.iloc[0] if len(modes) else pd.NA
        else:
            value = strategy
        if pd.notna(value):
            filled[column] = series.fillna(value)
    return df.assign(**filled)


def clean_dataset(
    df: pd.DataFrame,
    *,
    normalize_names: bool = False,
    strip: bool = True,
    drop_empty_rows_columns: bool = True,
    deduplicate: bool = True,
    convert: bool = True,
    fill: str | object | None = None,
    fill_columns: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Seçili temizlik adımlarını sırayla uygular; temiz veriyi ve adım adım değişiklik günlüğünü döndürür."""
    steps = [
        ("normalize_column_names", normalize_names, normalize_column_names),
        ("strip_whitespace", strip, strip_whitespace),
        ("drop_empty", drop_empty_rows_columns, drop_empty),
        ("drop_duplicate_rows", deduplicate, drop_duplicate_rows),
        ("convert_types", convert, convert_types),
        (f"fill_missing:{fill}", fill is not None, lambda data: fill_missing(data, fill, fill_columns)),
    ]
    log = []
    for name, enabled, step in steps:
        if not enabled:
            continue
        before = df
        df = step(df)
        changed_types = [c for c in df.columns if c in before and str(df[c].dtype) != str(before[c].dtype)]
        log.append(
            {
                "step": name,
                "rows_before": len(before),
                "rows_after": len(df),
                "columns_before": len(before.columns),
                "columns_after": len(df.columns),
                "missing_before": int(before.isna().sum().sum()),
                "missing_after": int(df.isna().sum().sum()),
                "changed_types": ", ".join(f"{c}:{before[c].dtype}->{df[c].dtype}" for c in changed_types),
            }
        )
    return df, pd.DataFrame(log)
