"""main.py argümansız çalıştırıldığında açılan numaralı, adım adım menü."""

import re
from collections.abc import Callable
from pathlib import Path

import pandas as pd

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
    sample_dataset,
    save_dataset,
    save_tables,
    validate,
    validation_passed,
)

LINE = "=" * 52


class Quit(Exception):
    """Kullanıcı menüden çıkmak istediğinde (0, q veya Ctrl+Z/Ctrl+D) fırlatılır."""


class Menu:
    def __init__(self, input_fn: Callable[[str], str] = input, print_fn: Callable[..., None] = print):
        self.input, self.print = input_fn, print_fn

    # ---- soru yardımcıları -------------------------------------------------
    def ask(self, text: str, default: str | None = None) -> str:
        hint = f" [{default}]" if default not in (None, "") else ""
        try:
            answer = self.input(f"{text}{hint}: ").strip()
        except EOFError as exc:
            raise Quit from exc
        return answer or (default or "")

    def yes_no(self, text: str, default: bool = True) -> bool:
        answer = self.ask(f"{text} (e/h)", "e" if default else "h").lower()
        return answer.startswith(("e", "y"))

    def choose(self, text: str, options: list[str], default: int = 1) -> int:
        """Numaralı seçenek gösterir, 1'den başlayan seçimi döndürür."""
        for number, option in enumerate(options, 1):
            self.print(f"  {number}) {option}")
        while True:
            answer = self.ask(text, str(default))
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return int(answer)
            self.print(f"  1 ile {len(options)} arasında bir sayı girin.")

    def ask_path(self, text: str, must_exist: bool = True, default: str | None = None) -> Path:
        while True:
            # Dosya Gezgini'nden sürükle-bırak yapılan yollar tırnaklı gelir.
            path = Path(self.ask(text, default).strip("\"'"))
            if str(path) in ("", "."):
                self.print("  Bir dosya yolu girin.")
            elif must_exist and not path.exists():
                self.print(f"  Dosya bulunamadı: {path}")
            else:
                return path

    def choose_columns(self, df: pd.DataFrame, text: str, allow_empty: bool = True) -> list[str] | None:
        """'1,3,5-7' gibi numaralarla veya adlarla sütun seçtirir; boş bırakılırsa None (tümü)."""
        columns = [str(c) for c in df.columns]
        width = len(str(len(columns)))
        for number, column in enumerate(columns, 1):
            self.print(f"  {number:>{width}}) {column}  ({df[df.columns[number - 1]].dtype})")
        while True:
            answer = self.ask(f"{text} (örn. 1,3,5-7; boş = {'tümü' if allow_empty else 'zorunlu'})")
            if not answer:
                if allow_empty:
                    return None
                self.print("  En az bir sütun seçin.")
                continue
            try:
                return parse_column_selection(answer, list(df.columns))
            except ValueError as exc:
                self.print(f"  {exc}")

    def load(self, text: str = "Veri dosyası") -> tuple[Path, pd.DataFrame]:
        path = self.ask_path(text)
        options = {}
        if path.suffix.lower() in {".xlsx", ".xls"}:
            sheets = list_sheets(path)
            if len(sheets) > 1:
                self.print("  Sayfalar:")
                options["sheet_name"] = sheets[self.choose("Sayfa", sheets) - 1]
        df = load_dataset(path, **options)
        self.print(f"  {len(df):,} satır, {len(df.columns)} sütun yüklendi.")
        return path, df

    def save_report(self, tables: dict[str, pd.DataFrame], default: str) -> None:
        if not self.yes_no("Rapor dosyaya kaydedilsin mi?"):
            return
        path = self.ask_path("Rapor yolu (.xlsx veya .html)", must_exist=False, default=default)
        self.print(f"  Rapor oluşturuldu: {save_tables(tables, path).resolve()}")

    # ---- menü eylemleri ----------------------------------------------------
    def analyze(self) -> None:
        path, df = self.load()
        if len(df) > 200_000 and self.yes_no(f"Veri büyük ({len(df):,} satır). Örneklem üzerinden çalışılsın mı?"):
            df = sample_dataset(df, n=int(self.ask("Örneklem satır sayısı", "100000")))
        columns = self.choose_columns(df, "Analiz edilecek sütunlar")
        top = int(self.ask("Frekans tablolarında kaç değer gösterilsin", "10"))
        tables = analyze_columns(df, columns, top)
        print_tables({k: tables[k] for k in ("overview", "quality", "numeric_summary", "categorical_summary")})
        self.save_report(tables, f"outputs/{path.stem}_analysis.xlsx")

    def compare(self) -> None:
        _, left = self.load("Birinci dosya")
        _, right = self.load("İkinci dosya")
        tables = {"schema_comparison": compare_schema(left, right)}
        print_tables(tables, max_rows=50)
        common = [c for c in left.columns if c in right.columns]
        if self.choose("Sütunlar nasıl eşleşsin", ["Aynı isimli ortak sütunlar", "Elle eşleştireceğim"]) == 1:
            pairs = [(c, c) for c in common]
        else:
            pairs = []
            self.print("  Birinci dosyanın sütunları:")
            left_columns = self.choose_columns(left, "Karşılaştırılacak sütunlar", allow_empty=False)
            for column in left_columns:
                match = self.ask(f"  '{column}' ikinci dosyada hangi sütun", column if column in right else None)
                if match not in right:
                    self.print(f"  '{match}' ikinci dosyada yok, atlandı.")
                    continue
                pairs.append((column, match))
        if pairs:
            tables["column_comparison"] = compare_columns(left, right, pairs)
            print_tables({"column_comparison": tables["column_comparison"]}, max_rows=50)
        if common and self.yes_no("Bir anahtar sütun üzerinden satır farkları da bulunsun mu?", False):
            keys = self.choose_columns(left[common], "Anahtar sütun(lar)", allow_empty=False)
            mismatches = compare_rows_by_key(left, right, keys, [c for c in common if c not in keys])
            tables["row_mismatches"] = mismatches
            self.print(f"  {len(mismatches):,} farklı/eksik satır bulundu.")
            print_tables({"row_mismatches": mismatches})
        self.save_report(tables, "outputs/comparison.xlsx")

    def clean(self) -> None:
        path, df = self.load()
        fill_choice = self.choose(
            "Eksik değerler",
            ["Dokunma", "Sayısalları medyanla doldur", "Sayısalları ortalamayla doldur", "En sık değerle doldur", "Eksik satırları sil", "Sabit bir değer yaz"],
        )
        fill = [None, "median", "mean", "mode", "drop", None][fill_choice - 1]
        if fill_choice == 6:
            fill = self.ask("Yazılacak değer", "0")
        cleaned, log = clean_dataset(
            df,
            normalize_names=self.yes_no("Sütun adları snake_case yapılsın mı (Müşteri Adı -> musteri_adi)?", False),
            deduplicate=self.yes_no("Tekrar eden satırlar silinsin mi?"),
            convert=self.yes_no("Metin olarak okunan sayı/tarih/evet-hayır sütunları dönüştürülsün mü?"),
            fill=fill,
        )
        print_tables({"clean_log": log})
        output = self.ask_path("Temiz veri nereye kaydedilsin", must_exist=False, default=f"outputs/{path.stem}_clean.csv")
        self.print(f"  Kaydedildi: {save_dataset(cleaned, output).resolve()}")

    def validate(self) -> None:
        _, df = self.load()
        rules = load_rules(self.ask_path("Kural dosyası (.json)"))
        report = validate(df, rules)
        print_tables({"validation": report}, max_rows=len(report))
        failed = int((~report["passed"]).sum()) if len(report) else 0
        self.print(f"\n  Sonuç: {'BAŞARILI' if validation_passed(report) else f'BAŞARISIZ ({failed} kural)'}")
        self.save_report({"validation": report}, "outputs/validation.xlsx")

    def profile(self) -> None:
        path = self.ask_path("CSV dosyası")
        chunksize = int(self.ask("Her parçada kaç satır okunsun", "100000"))
        tables = profile_csv_in_chunks(path, chunksize=chunksize)
        print_tables(tables, max_rows=50)
        self.save_report(tables, f"outputs/{path.stem}_profile.xlsx")

    def sql(self) -> None:
        path, df = self.load()
        default = "Query" if "Query" in df else None
        column = self.ask("Sorgu sütunu", default)
        size = self.choose("Özel karakter kombinasyonları", ["Yok", "2'li (~870 sütun, önerilen)", "2'li ve 3'lü (~25 bin sütun)"], 2)
        result = add_sql_features(df, column, ((), (2,), (2, 3))[size - 1])
        self.print(f"  {len(result.columns) - len(df.columns)} özellik sütunu eklendi.")
        output = self.ask_path("Nereye kaydedilsin", must_exist=False, default=f"outputs/{path.stem}_sql_features.csv")
        self.print(f"  Kaydedildi: {save_dataset(result, output).resolve()}")

    def columns(self) -> None:
        _, df = self.load()
        print_tables({"columns": column_table(df)}, max_rows=len(df.columns))

    # ---- ana döngü ---------------------------------------------------------
    def actions(self) -> list[tuple[str, Callable[[], None]]]:
        return [
            ("Sütunları ve tiplerini listele", self.columns),
            ("Veri setini analiz et ve rapor oluştur", self.analyze),
            ("İki veri setini karşılaştır", self.compare),
            ("Veri setini temizle ve kaydet", self.clean),
            ("Kural dosyasıyla doğrula", self.validate),
            ("Büyük CSV'yi parça parça profille", self.profile),
            ("SQL sorgularından özellik çıkar", self.sql),
        ]

    def run(self) -> None:
        actions = self.actions()
        while True:
            self.print(f"\n{LINE}\n  Dataset Analysis Toolset\n{LINE}")
            for number, (title, _) in enumerate(actions, 1):
                self.print(f"  {number}) {title}")
            self.print("  0) Çıkış")
            try:
                answer = self.ask("\nSeçiminiz")
                if answer.lower() in {"0", "q", "çıkış", "exit"}:
                    raise Quit
                if not answer.isdigit() or not 1 <= int(answer) <= len(actions):
                    self.print("  Geçersiz seçim.")
                    continue
                title, action = actions[int(answer) - 1]
                self.print(f"\n--- {title} ---")
                action()
            except Quit:
                self.print("Görüşmek üzere.")
                return
            except KeyboardInterrupt:
                self.print("\n  İşlem iptal edildi.")
            except (FileNotFoundError, KeyError, ValueError, UnicodeDecodeError) as exc:
                self.print(f"  Hata: {exc.args[0] if isinstance(exc, KeyError) else exc}")


def parse_column_selection(answer: str, columns: list) -> list:
    """'1,3,5-7', 'age, city' veya karışık girdiyi sütun listesine çevirir."""
    selected = []
    for part in filter(None, (p.strip() for p in answer.split(","))):
        if re.fullmatch(r"\d+-\d+", part):
            start, end = map(int, part.split("-"))
            numbers = range(start, end + 1)
        elif part.isdigit() and part not in map(str, columns):
            numbers = [int(part)]
        elif part in map(str, columns):
            selected.append(next(c for c in columns if str(c) == part))
            continue
        else:
            raise ValueError(f"Bilinmeyen sütun: {part}")
        for number in numbers:
            if not 1 <= number <= len(columns):
                raise ValueError(f"Sütun numarası 1 ile {len(columns)} arasında olmalı: {number}")
            selected.append(columns[number - 1])
    return list(dict.fromkeys(selected))


def run_menu() -> None:
    Menu().run()
