"""CSV, Excel, Parquet ve JSON veri setlerini tek fonksiyonla okur."""

import csv
from pathlib import Path

import pandas as pd

CSV_DELIMITERS = ",;\t|"
CSV_ENCODINGS = ("utf-8-sig", "cp1254", "latin-1")


def _sniff_sep(path: Path) -> str:
    """İlk 64 KB'tan ayracı tahmin eder; tek sütunlu dosyalarda virgüle düşer."""
    sample = path.read_bytes()[: 64 * 1024].decode("utf-8", errors="ignore")
    try:
        return csv.Sniffer().sniff(sample, delimiters=CSV_DELIMITERS).delimiter
    except csv.Error:
        return ","


def _read_csv(path: Path, sep: str | None = None, **kwargs) -> pd.DataFrame:
    """Ayraç verilmezse tahmin eder; encoding verilmezse UTF-8, Türkçe ve Latin-1 dener."""
    sep = sep or _sniff_sep(path)
    encodings = [kwargs.pop("encoding")] if "encoding" in kwargs else CSV_ENCODINGS
    for encoding in encodings:
        try:
            return pd.read_csv(path, sep=sep, encoding=encoding, **kwargs)
        except UnicodeDecodeError as exc:
            error = exc
    raise error


def load_dataset(path: str | Path, **kwargs) -> pd.DataFrame:
    """Dosya uzantısına göre uygun pandas okuyucusunu seçer."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Veri seti bulunamadı: {path}")

    readers = {
        ".csv": lambda: _read_csv(path, **kwargs),
        ".tsv": lambda: _read_csv(path, **{"sep": "\t", **kwargs}),
        ".xlsx": lambda: pd.read_excel(path, **kwargs),
        ".xls": lambda: pd.read_excel(path, **kwargs),
        ".parquet": lambda: pd.read_parquet(path, **kwargs),
        ".json": lambda: pd.read_json(path, **kwargs),
    }
    try:
        reader = readers[path.suffix.lower()]
    except KeyError as exc:
        raise ValueError(f"Desteklenmeyen dosya türü: {path.suffix}") from exc
    return reader()
