import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from dataset_tools import (
    add_sql_features,
    clean_dataset,
    compare_rows_by_key,
    convert_types,
    extract_sql_features,
    fill_missing,
    list_sheets,
    load_dataset,
    normalize_column_names,
    save_dataset,
)
from interactive import Menu, parse_column_selection


class CleaningTest(unittest.TestCase):
    def test_normalize_column_names(self):
        df = pd.DataFrame(columns=["Müşteri Adı", "müşteri adı", "Şehir/İlçe", "  "])
        self.assertEqual(list(normalize_column_names(df).columns), ["musteri_adi", "musteri_adi_2", "sehir_ilce", "column"])

    def test_convert_types(self):
        df = pd.DataFrame(
            {
                "amount": ["1.234,5", "10", None],
                "flag": ["evet", "Hayır", None],
                "date": ["01.02.2024", "2024-04-01", None],
                "code": ["001", "002", "abc"],
            }
        )
        out = convert_types(df)
        self.assertEqual(out["amount"].tolist()[:2], [1234.5, 10.0])
        self.assertEqual(out["flag"].tolist()[:2], [True, False])
        self.assertEqual(out["date"].dt.month.tolist()[:2], [2, 4])
        self.assertEqual(out["code"].tolist(), ["001", "002", "abc"])

    def test_convert_types_keeps_ambiguous_and_identifier_values(self):
        cases = {
            "dotted_dates": (["01.04.2024", "31.12.2024"], "datetime64"),
            "mixed_decimals": (["1.234,56", "1,5", "1.5"], "str"),
            "phones": (["05321234567", "05001234567"], "str"),
            "zip": (["00123", "00456"], "str"),
        }
        out = convert_types(pd.DataFrame({name: pd.Series(values, dtype=object) for name, (values, _) in cases.items()}))
        for name, (_, kind) in cases.items():
            if kind == "str":
                self.assertEqual(out[name].dropna().tolist(), cases[name][0], name)
            else:
                self.assertTrue(str(out[name].dtype).startswith(kind), name)
        big = convert_types(pd.DataFrame({"x": ["9007199254740993"]}))["x"]
        self.assertEqual(big.iloc[0], 9007199254740993)

    def test_fill_constant_matches_column_type(self):
        df = pd.DataFrame({"n": pd.Series([1, None], dtype="Int64"), "b": pd.Series([True, None], dtype="boolean")})
        self.assertEqual(fill_missing(df, "0").to_dict("list"), {"n": [1, 0], "b": [True, False]})
        with self.assertRaises(ValueError):
            fill_missing(df, "bilinmiyor")

    def test_fill_missing_strategies(self):
        df = pd.DataFrame({"x": [1, None, 3], "city": ["A", None, "A"]})
        self.assertEqual(fill_missing(df, "median")["x"].tolist(), [1, 2, 3])
        self.assertTrue(fill_missing(df, "median")["city"].isna().any())
        self.assertEqual(fill_missing(df, "mode")["city"].tolist(), ["A", "A", "A"])
        self.assertEqual(len(fill_missing(df, "drop")), 2)
        self.assertEqual(fill_missing(df, "?", ["city"])["city"].tolist(), ["A", "?", "A"])

    def test_clean_dataset_log(self):
        df = pd.DataFrame({"a": [" x ", " x ", None], "b": ["1", "1", None], "empty": [None, None, None]})
        cleaned, log = clean_dataset(df)
        self.assertEqual(cleaned.to_dict("list"), {"a": ["x"], "b": [1]})
        self.assertEqual(log["step"].tolist(), ["strip_whitespace", "drop_empty", "drop_duplicate_rows", "convert_types"])
        self.assertEqual(log.iloc[-1]["rows_after"], 1)


class SqlFeaturesTest(unittest.TestCase):
    def test_extract_and_add(self):
        features = extract_sql_features("SELECT * FROM u WHERE id='1' OR 1=1 -- x")
        self.assertEqual(features["Has_or_1=1"], 1)
        self.assertEqual(features["NumSingleQuotes"], 2)
        self.assertEqual(len(extract_sql_features("x", ())), len(features) - len([k for k in features if k.startswith("Combo_")]))
        df = add_sql_features(pd.DataFrame({"Query": ["select 1", None]}))
        self.assertEqual(df.loc[1, "Length"], 0)
        with self.assertRaises(KeyError):
            add_sql_features(df, "missing")
        with self.assertRaises(ValueError):
            add_sql_features(df)  # özellikler zaten eklenmiş


class IoAndKeyTest(unittest.TestCase):
    def test_save_round_trip_and_sheets(self):
        df = pd.DataFrame({"ad": ["Ömer", "Şule"], "n": [1, 2]})
        with tempfile.TemporaryDirectory() as directory:
            for suffix in (".csv", ".tsv", ".json", ".xlsx", ".parquet"):
                path = save_dataset(df, Path(directory) / f"out{suffix}")
                self.assertEqual(load_dataset(path)["ad"].tolist(), ["Ömer", "Şule"], suffix)
            book = Path(directory) / "book.xlsx"
            with pd.ExcelWriter(book) as writer:
                df.to_excel(writer, sheet_name="first", index=False)
                df.assign(n=[3, 4]).to_excel(writer, sheet_name="second", index=False)
            self.assertEqual(list_sheets(book), ["first", "second"])
            result = subprocess.run(
                [sys.executable, "main.py", str(book), "--sheet", "second", "--output", str(Path(directory) / "r.html")],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_composite_key(self):
        a = pd.DataFrame({"y": [2024, 2024], "m": [1, 2], "v": [1, 2]})
        b = pd.DataFrame({"y": [2024, 2024], "m": [1, 2], "v": [1, 5]})
        mismatches = compare_rows_by_key(a, b, ["y", "m"], ["v"])
        self.assertEqual(mismatches[["y", "m"]].values.tolist(), [[2024, 2]])
        with self.assertRaises(ValueError):
            compare_rows_by_key(a, b, ["y"], ["v"])
        unsigned = pd.DataFrame({"id": pd.Series([2**63 + 1], dtype="uint64"), "v": ["x"]})
        self.assertEqual(len(compare_rows_by_key(unsigned, unsigned.copy(), ["id"], ["v"])), 0)


class CommandTest(unittest.TestCase):
    def run_main(self, *args):
        return subprocess.run([sys.executable, "main.py", *map(str, args)], capture_output=True, encoding="utf-8", errors="replace")

    def test_clean_validate_sql_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "raw.csv"
            source.write_text("id;age;Query\n1;20;select 1\n1;20;select 1\n2;;x' or 1=1\n", encoding="utf-8")
            clean = self.run_main("clean", source, "--output", directory / "clean.csv", "--fill", "median")
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertEqual(len(pd.read_csv(directory / "clean.csv")), 2)

            rules = directory / "rules.json"
            rules.write_text(json.dumps({"columns": {"age": {"min": 0, "max": 10}}}), encoding="utf-8")
            check = self.run_main("validate", directory / "clean.csv", "--rules", rules)
            self.assertEqual(check.returncode, 2, check.stderr)

            sql = self.run_main("sql", source, "--combo", "0", "--output", directory / "sql.csv")
            self.assertNotEqual(sql.returncode, 0)
            sql = self.run_main("sql", source, "--output", directory / "sql.csv")
            self.assertEqual(sql.returncode, 0, sql.stderr)
            orphan = self.run_main(source, "--key", "id")
            self.assertIn("--dataset2", orphan.stderr)


class MenuTest(unittest.TestCase):
    def run_menu(self, answers):
        answers, output = iter(answers), []

        def answer(_):
            try:
                return next(answers)
            except StopIteration:
                raise EOFError from None

        Menu(input_fn=answer, print_fn=lambda *a, **_: output.append(" ".join(map(str, a)))).run()
        return "\n".join(output)

    def test_column_selection(self):
        columns = ["a", "b", "c", "d", "2"]
        self.assertEqual(parse_column_selection("1, 3-4", columns), ["a", "c", "d"])
        self.assertEqual(parse_column_selection("b,2,b", columns), ["b", "2"])
        with self.assertRaises(ValueError):
            parse_column_selection("9", columns)

    def test_menu_flows(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "data.csv"
            pd.DataFrame({"id": [1, 2, 2], "city": ["A", "B", "B"]}).to_csv(source, index=False)
            clean_path = Path(directory) / "clean.csv"
            text = self.run_menu(
                [
                    "x",  # geçersiz seçim
                    "1", f'"{source}"',  # sütunları listele, tırnaklı yol
                    "4", "missing.csv", str(source), "1", "h", "e", "e", str(clean_path),  # temizle
                    "2", str(source), "1, 2", "5", "h",  # analiz
                    "0",
                ]
            )
            self.assertIn("Geçersiz seçim", text)
            self.assertIn("Dosya bulunamadı", text)
            self.assertEqual(len(pd.read_csv(clean_path)), 2)
            self.assertIn("Görüşmek üzere", text)

    def test_menu_survives_errors_and_eof(self):
        with tempfile.TemporaryDirectory() as directory:
            unsupported = Path(directory) / "notes.txt"
            unsupported.write_text("x", encoding="utf-8")
            text = self.run_menu(["1", str(unsupported)])  # hata menüyü kapatmaz, girdi bitince çıkar
        self.assertIn("Hata: Desteklenmeyen dosya türü", text)
        self.assertIn("Görüşmek üzere", text)

if __name__ == "__main__":
    unittest.main()
