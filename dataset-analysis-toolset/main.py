"""Komut satırından modüler dataset araçlarını çağıran giriş noktası.

Argümansız çalıştırılırsa interaktif menü açılır.
"""

import argparse
import sys
from pathlib import Path

from dataset_tools import (
    add_sql_features,
    analyze_columns,
    clean_dataset,
    column_table,
    compare_columns,
    compare_rows_by_key,
    compare_schema,
    list_sheets,
    load_dataset,
    load_rules,
    print_tables,
    profile_csv_in_chunks,
    save_dataset,
    save_tables,
    validate,
    validation_passed,
)

COMMANDS = ("clean", "validate", "profile", "sql", "sheets")


def parse_pair(value: str) -> tuple[str, str]:
    parts = value.replace(":", "=", 1).split("=", 1)
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("Sütun çifti left=right biçiminde olmalı")
    return parts[0], parts[1]


def add_input_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sep", help="CSV ayracı; verilmezse otomatik tahmin edilir")
    parser.add_argument("--encoding", help="CSV kodlaması; verilmezse utf-8, cp1254 ve latin-1 denenir")
    parser.add_argument("--decimal", help="CSV ondalık ayracı; örn. Türkçe Excel çıktıları için ,")
    parser.add_argument("--sheet", help="Excel sayfa adı veya 0'dan başlayan sırası")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Modüler dataset analiz araç seti",
        epilog=f"Diğer komutlar: {', '.join(COMMANDS)} (örn. python main.py clean -h). Argümansız çalıştırınca menü açılır.",
    )
    parser.add_argument("dataset1", help="Birinci CSV/Excel/Parquet/JSON dosyası")
    parser.add_argument("--dataset2", help="Karşılaştırılacak ikinci dosya")
    parser.add_argument("--sheet2", help="İkinci Excel dosyasının sayfası")
    parser.add_argument("--columns", nargs="+", help="Birinci veri setinde analiz edilecek sütunlar")
    parser.add_argument("--pair", action="append", type=parse_pair, default=[], help="Karşılaştırma çifti; örn. age=customer_age")
    parser.add_argument("--key", nargs="+", help="Satır karşılaştırmasında kullanılacak tekil anahtar (birden çok sütun olabilir)")
    parser.add_argument("--row-columns", nargs="+", help="Anahtar bazında karşılaştırılacak ortak sütunlar")
    parser.add_argument("--top", type=int, default=10, help="Frekans tablolarındaki değer sayısı")
    parser.add_argument("--output", default="outputs/analysis_report.xlsx", help=".xlsx veya .html rapor yolu")
    add_input_options(parser)
    return parser


def build_command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main.py", description="Temizleme, doğrulama, profil ve SQL özellik komutları")
    commands = parser.add_subparsers(dest="command", required=True)

    clean = commands.add_parser("clean", help="Veri setini temizleyip kaydet")
    clean.add_argument("dataset")
    clean.add_argument("--output", required=True, help="Temiz veri dosyası (.csv/.xlsx/.parquet/.json)")
    clean.add_argument("--log", help="Değişiklik günlüğü raporu (.xlsx/.html)")
    clean.add_argument("--normalize-names", action="store_true", help="Sütun adlarını snake_case yap")
    clean.add_argument("--keep-duplicates", action="store_true", help="Tekrar satırları silme")
    clean.add_argument("--no-convert", action="store_true", help="Tip dönüşümü yapma")
    clean.add_argument("--fill", help="Eksik değer stratejisi: mean, median, mode, drop veya sabit değer")
    clean.add_argument("--fill-columns", nargs="+", help="Doldurulacak sütunlar (varsayılan: tümü)")

    check = commands.add_parser("validate", help="JSON kurallarıyla doğrula; hata varsa çıkış kodu 2")
    check.add_argument("dataset")
    check.add_argument("--rules", required=True, help="Kural dosyası (.json)")
    check.add_argument("--output", help="Doğrulama raporu (.xlsx/.html)")

    profile = commands.add_parser("profile", help="Büyük CSV'yi belleğe almadan parça parça profille")
    profile.add_argument("dataset")
    profile.add_argument("--chunksize", type=int, default=100_000)
    profile.add_argument("--output", help="Profil raporu (.xlsx/.html)")

    sql = commands.add_parser("sql", help="SQL sorgu sütunundan injection özellikleri çıkar")
    sql.add_argument("dataset")
    sql.add_argument("--column", default="Query", help="Sorgu sütunu")
    sql.add_argument("--combo", type=int, nargs="+", default=[2], help="Özel karakter kombinasyon uzunlukları (3-4 çok sütun üretir)")
    sql.add_argument("--output", required=True)

    sheets = commands.add_parser("sheets", help="Excel dosyasındaki sayfaları listele")
    sheets.add_argument("dataset")

    for sub in (clean, check, profile, sql):
        add_input_options(sub)
    return parser


def load(path: str, args: argparse.Namespace, sheet: str | None = None):
    """CSV seçeneklerini yalnızca CSV/TSV, sayfa seçimini yalnızca Excel dosyalarına iletir."""
    suffix = Path(path).suffix.lower()
    if suffix in {".csv", ".tsv"}:
        options = {name: getattr(args, name) for name in ("sep", "encoding", "decimal") if getattr(args, name, None)}
        return load_dataset(path, **options)
    if suffix in {".xlsx", ".xls"} and sheet is not None:
        return load_dataset(path, sheet_name=int(sheet) if sheet.isdigit() else sheet)
    return load_dataset(path)


def run(args: argparse.Namespace) -> None:
    if (args.key or args.row_columns or args.pair or args.sheet2) and not args.dataset2:
        raise ValueError("--key, --row-columns, --pair ve --sheet2 için --dataset2 de verilmeli")
    if args.row_columns and not args.key:
        raise ValueError("--row-columns için --key de verilmeli")
    first = load(args.dataset1, args, args.sheet)
    print_tables({"dataset1_columns": column_table(first)}, max_rows=len(first.columns))
    tables = {f"dataset1_{name}": table for name, table in analyze_columns(first, args.columns, args.top).items()}

    if args.dataset2:
        second = load(args.dataset2, args, args.sheet2)
        print_tables({"dataset2_columns": column_table(second)}, max_rows=len(second.columns))
        second_columns = [right for _, right in args.pair] if args.pair else ([c for c in (args.columns or []) if c in second] or None)
        tables |= {f"dataset2_{name}": table for name, table in analyze_columns(second, second_columns, args.top).items()}
        tables |= {"schema_comparison": compare_schema(first, second)}
        pairs = args.pair or [(column, column) for column in (args.columns or first.columns) if column in second]
        if pairs:
            tables["column_comparison"] = compare_columns(first, second, pairs)
        if args.key:
            row_columns = args.row_columns or [c for c in first.columns if c in second and c not in args.key]
            tables["row_mismatches"] = compare_rows_by_key(first, second, args.key, row_columns)

    output = save_tables(tables, args.output)
    print(f"\nRapor oluşturuldu: {output.resolve()}")


def run_command(args: argparse.Namespace) -> int:
    if args.command == "sheets":
        print("\n".join(f"{i}: {name}" for i, name in enumerate(list_sheets(args.dataset))))
        return 0
    if args.command == "profile":
        options = {name: getattr(args, name) for name in ("sep", "encoding", "decimal") if getattr(args, name)}
        tables = profile_csv_in_chunks(args.dataset, chunksize=args.chunksize, **options)
        print_tables(tables, max_rows=50)
        if args.output:
            print(f"\nRapor oluşturuldu: {save_tables(tables, args.output).resolve()}")
        return 0

    df = load(args.dataset, args, args.sheet)
    if args.command == "clean":
        cleaned, log = clean_dataset(
            df,
            normalize_names=args.normalize_names,
            deduplicate=not args.keep_duplicates,
            convert=not args.no_convert,
            fill=args.fill,
            fill_columns=args.fill_columns,
        )
        print_tables({"clean_log": log})
        print(f"\nTemiz veri kaydedildi: {save_dataset(cleaned, args.output).resolve()}")
        if args.log:
            save_tables({"clean_log": log, "columns": column_table(cleaned)}, args.log)
        return 0
    if args.command == "validate":
        report = validate(df, load_rules(args.rules))
        print_tables({"validation": report}, max_rows=len(report))
        if args.output:
            save_tables({"validation": report}, args.output)
        passed = validation_passed(report)
        print("\nDoğrulama BAŞARILI" if passed else "\nDoğrulama BAŞARISIZ")
        return 0 if passed else 2
    if args.command == "sql":
        result = add_sql_features(df, args.column, tuple(args.combo))
        print(f"{len(result.columns) - len(df.columns)} özellik sütunu eklendi.")
        print(f"Kaydedildi: {save_dataset(result, args.output).resolve()}")
        return 0
    raise ValueError(f"Bilinmeyen komut: {args.command}")


def main(argv: list[str] | None = None) -> None:
    # Türkçe karakterleri desteklemeyen Windows konsollarında print çökmesin.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        from interactive import run_menu

        run_menu()
        return
    try:
        if argv[0] in COMMANDS:
            sys.exit(run_command(build_command_parser().parse_args(argv)))
        run(build_parser().parse_args(argv))
    except (FileNotFoundError, KeyError, ValueError, UnicodeDecodeError) as exc:
        sys.exit(f"Hata: {exc.args[0] if isinstance(exc, KeyError) else exc}")


if __name__ == "__main__":
    main()
