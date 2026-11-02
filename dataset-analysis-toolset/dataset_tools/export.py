"""Birden fazla pandas tablosunu konsola, Excel'e veya HTML'e çıkarır."""

import html
import re
from pathlib import Path

import pandas as pd


def _sheet_names(names) -> dict[str, str]:
    result, used = {}, set()
    for original in names:
        base = re.sub(r"[\\/*?:\[\]]", "_", str(original))[:31] or "table"
        candidate, number = base, 2
        while candidate.lower() in used:
            suffix = f"_{number}"
            candidate, number = f"{base[:31 - len(suffix)]}{suffix}", number + 1
        result[original], used = candidate, used | {candidate.lower()}
    return result


def save_tables(tables: dict[str, pd.DataFrame], path: str | Path) -> Path:
    """Tablo sözlüğünü .xlsx veya tek dosyalık .html rapora kaydeder."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = {name: frame for name, frame in tables.items() if isinstance(frame, pd.DataFrame)}
    if path.suffix.lower() == ".xlsx":
        names = _sheet_names(frames)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for name, frame in frames.items():
                # Excel saat dilimli tarih saklayamaz; değerleri koruyup dilim bilgisini düşürür.
                tz_columns = frame.select_dtypes(include="datetimetz").columns
                frame = frame.assign(**{c: frame[c].dt.tz_localize(None) for c in tz_columns})
                frame.to_excel(writer, sheet_name=names[name], index=False)
    elif path.suffix.lower() == ".html":
        sections = "\n".join(f"<h2>{html.escape(str(name))}</h2>{frame.to_html(index=False)}" for name, frame in frames.items())
        path.write_text(f"<!doctype html><meta charset='utf-8'><style>body{{font:14px Arial;margin:32px}}table{{border-collapse:collapse;margin-bottom:32px}}th,td{{border:1px solid #bbb;padding:6px}}th{{background:#eee}}</style><h1>Dataset Analysis Report</h1>{sections}", encoding="utf-8")
    else:
        raise ValueError("Çıktı uzantısı .xlsx veya .html olmalı")
    return path


def print_tables(tables: dict[str, pd.DataFrame], max_rows: int = 20) -> None:
    """Tabloları başlıklarıyla konsola yazdırır."""
    for name, frame in tables.items():
        print(f"\n[{name}]\n{frame.head(max_rows).to_string(index=False)}")
