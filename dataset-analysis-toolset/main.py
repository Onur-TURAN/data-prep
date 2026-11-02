"""Komut satırından modüler dataset araçlarını çağıran giriş noktası."""

import argparse
import sys
from pathlib import Path

from dataset_tools import analyze_columns, column_table, compare_columns, compare_rows_by_key, compare_schema, load_dataset, print_tables, save_tables


def parse_pair(value: str) -> tuple[str, str]:
    parts = value.replace(":", "=", 1).split("=", 1)
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("Sütun çifti left=right biçiminde olmalı")
    return parts[0], parts[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Modüler dataset analiz araç seti")
    parser.add_argument("dataset1", help="Birinci CSV/Excel/Parquet/JSON dosyası")
    parser.add_argument("--dataset2", help="Karşılaştırılacak ikinci dosya")
    parser.add_argument("--columns", nargs="+", help="Birinci veri setinde analiz edilecek sütunlar")
    parser.add_argument("--pair", action="append", type=parse_pair, default=[], help="Karşılaştırma çifti; örn. age=customer_age")
    parser.add_argument("--key", help="Satır karşılaştırmasında kullanılacak tekil anahtar")
    parser.add_argument("--row-columns", nargs="+", help="Anahtar bazında karşılaştırılacak ortak sütunlar")
    parser.add_argument("--top", type=int, default=10, help="Frekans tablolarındaki değer sayısı")
    parser.add_argument("--output", default="outputs/analysis_report.xlsx", help=".xlsx veya .html rapor yolu")
    parser.add_argument("--sep", help="CSV ayracı; verilmezse otomatik tahmin edilir")
    parser.add_argument("--encoding", help="CSV kodlaması; verilmezse utf-8, cp1254 ve latin-1 denenir")
    parser.add_argument("--decimal", help="CSV ondalık ayracı; örn. Türkçe Excel çıktıları için ,")
    return parser


def load(path: str, args: argparse.Namespace):
    """CSV seçeneklerini yalnızca CSV/TSV dosyalarına iletir."""
    options = {name: getattr(args, name) for name in ("sep", "encoding", "decimal") if getattr(args, name)}
    return load_dataset(path, **options) if Path(path).suffix.lower() in {".csv", ".tsv"} else load_dataset(path)


def run(args: argparse.Namespace) -> None:
    first = load(args.dataset1, args)
    print_tables({"dataset1_columns": column_table(first)}, max_rows=len(first.columns))
    tables = {f"dataset1_{name}": table for name, table in analyze_columns(first, args.columns, args.top).items()}

    if args.dataset2:
        second = load(args.dataset2, args)
        print_tables({"dataset2_columns": column_table(second)}, max_rows=len(second.columns))
        second_columns = [right for _, right in args.pair] if args.pair else ([c for c in (args.columns or []) if c in second] or None)
        tables |= {f"dataset2_{name}": table for name, table in analyze_columns(second, second_columns, args.top).items()}
        tables |= {"schema_comparison": compare_schema(first, second)}
        pairs = args.pair or [(column, column) for column in (args.columns or first.columns) if column in second]
        if pairs:
            tables["column_comparison"] = compare_columns(first, second, pairs)
        if args.key:
            row_columns = args.row_columns or [c for c in first.columns if c in second and c != args.key]
            tables["row_mismatches"] = compare_rows_by_key(first, second, args.key, row_columns)

    output = save_tables(tables, args.output)
    print(f"\nRapor oluşturuldu: {output.resolve()}")


def main() -> None:
    args = build_parser().parse_args()
    try:
        run(args)
    except (FileNotFoundError, KeyError, ValueError, UnicodeDecodeError) as exc:
        sys.exit(f"Hata: {exc.args[0] if isinstance(exc, KeyError) else exc}")


if __name__ == "__main__":
    main()
