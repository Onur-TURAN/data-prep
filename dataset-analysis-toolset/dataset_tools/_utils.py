"""Modüller arasında kullanılan küçük doğrulama yardımcıları."""

from collections.abc import Iterable

import pandas as pd

UNHASHABLE = (list, dict, set)


def hashable_cells(df: pd.DataFrame) -> pd.DataFrame:
    """JSON'dan gelen liste/sözlük hücrelerini metne çevirir; nunique ve value_counts çökmesin."""
    converted = {}
    for column in df.columns[df.dtypes == object]:
        mask = df[column].map(lambda value: isinstance(value, UNHASHABLE))
        if mask.any():
            converted[column] = df[column].where(~mask, df[column][mask].map(str))
    return df.assign(**converted) if converted else df


def select_columns(df: pd.DataFrame, columns: Iterable[str] | None) -> pd.DataFrame:
    """İstenen sütunları doğrular ve seçer; None ise tümünü döndürür."""
    if columns is None:
        return hashable_cells(df)
    columns = list(columns)
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise KeyError(f"Bulunamayan sütunlar: {missing}")
    return hashable_cells(df.loc[:, columns])
