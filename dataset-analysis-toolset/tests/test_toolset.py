import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from dataset_tools import analyze_columns, column_table, compare_columns, compare_rows_by_key, compare_schema, load_dataset, save_tables


class DatasetToolsTest(unittest.TestCase):
    def setUp(self):
        self.left = pd.DataFrame({"id": [1, 2, 3], "age": [20, 30, None], "city": ["A", "B", "B"]})
        self.right = pd.DataFrame({"id": [1, 2, 4], "age": [20, 31, 40], "city": ["A", "C", "D"]})

    def test_load_and_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.csv"
            self.left.to_csv(path, index=False)
            loaded = load_dataset(path)
        self.assertEqual(list(column_table(loaded)["column"]), ["id", "age", "city"])

    def test_analysis_tables(self):
        tables = analyze_columns(self.left, ["age", "city"], top_n=2)
        self.assertIn("numeric_summary", tables)
        self.assertIn("frequency_city", tables)
        self.assertEqual(tables["frequency_city"].iloc[0]["count"], 2)

    def test_dataset_comparisons(self):
        self.assertIn("dtype_match", compare_schema(self.left, self.right))
        comparison = compare_columns(self.left, self.right, [("city", "city")])
        self.assertEqual(comparison.iloc[0]["shared_unique"], 1)

    def test_key_comparison(self):
        mismatches = compare_rows_by_key(self.left, self.right, "id", ["age", "city"])
        self.assertEqual(set(mismatches["id"]), {2, 3, 4})

    def test_html_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = save_tables({"columns": column_table(self.left)}, Path(directory) / "report.html")
            self.assertTrue(path.exists())
            self.assertIn("Dataset Analysis Report", path.read_text(encoding="utf-8"))

    def test_excel_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = save_tables({"columns": column_table(self.left)}, Path(directory) / "report.xlsx")
            self.assertEqual(pd.read_excel(path)["column"].tolist(), ["id", "age", "city"])

    def test_main_command(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            first, second, report = directory / "a.csv", directory / "b.csv", directory / "report.xlsx"
            self.left.to_csv(first, index=False)
            self.right.to_csv(second, index=False)
            result = subprocess.run(
                [sys.executable, "main.py", str(first), "--dataset2", str(second), "--pair", "city=city", "--output", str(report)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(report.exists())

    def test_main_reports_errors_without_traceback(self):
        result = subprocess.run([sys.executable, "main.py", "missing.csv"], check=False, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)

    def test_csv_single_column_and_turkish_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            single, turkish = Path(directory) / "single.csv", Path(directory) / "tr.csv"
            single.write_text("name\nali\nveli\n", encoding="utf-8")
            turkish.write_text("ad;şehir\nÖmer;İzmir\n", encoding="cp1254")
            self.assertEqual(load_dataset(single).columns.tolist(), ["name"])
            self.assertEqual(load_dataset(turkish).columns.tolist(), ["ad", "şehir"])

    def test_numeric_values_match_across_int_and_float(self):
        comparison = compare_columns(self.left, self.right, ["age"])
        self.assertEqual(comparison.iloc[0]["shared_unique"], 1)

    def test_key_comparison_with_different_key_types(self):
        right = self.right.assign(id=self.right["id"].astype(str))
        mismatches = compare_rows_by_key(self.left, right, "id", ["city"])
        self.assertEqual(set(mismatches["id"]), {"2", "3", "4"})

    def test_null_to_value_change_is_reported(self):
        a = pd.DataFrame({"id": [1], "v": pd.Series([pd.NA], dtype="Int64")})
        b = pd.DataFrame({"id": [1], "v": pd.Series([7], dtype="Int64")})
        self.assertEqual(len(compare_rows_by_key(a, b, "id", ["v"])), 1)

    def test_large_integers_are_not_rounded(self):
        a, b = pd.DataFrame({"id": [1, 2], "x": [2**53 + 1, 0]}), pd.DataFrame({"id": [1, 3], "x": [2**53, 0]})
        self.assertEqual(compare_columns(a, b, ["x"]).iloc[0]["shared_unique"], 1)
        self.assertIn(1, set(compare_rows_by_key(a, b, "id", ["x"])["id"]))

    def test_key_collision_after_type_conversion(self):
        a = pd.DataFrame({"id": pd.Series([1, "1"], dtype=object), "v": [7, 7]})
        with self.assertRaises(ValueError):
            compare_rows_by_key(a, pd.DataFrame({"id": [1], "v": [7]}), "id", ["v"])

    def test_awkward_column_names_and_dtypes(self):
        self.assertIn("correlation", analyze_columns(pd.DataFrame({"column": [1, 2]})))
        df = pd.DataFrame({"row_status": [1], "v": [1]})
        self.assertEqual(len(compare_rows_by_key(df, df, "row_status", ["v"])), 0)
        a = pd.DataFrame({"id": [1], "v": pd.Categorical(["a"], categories=["a", "b"])})
        b = pd.DataFrame({"id": [1], "v": pd.Categorical(["a"], categories=["a", "c"])})
        self.assertEqual(len(compare_rows_by_key(a, b, "id", ["v"])), 0)
        empty = pd.DataFrame({"x": pd.Series([pd.NA], dtype="Int64")})
        self.assertIsNone(compare_columns(empty, empty, ["x"]).iloc[0]["left_mean"])
        unused = pd.DataFrame({"x": pd.Categorical([None], categories=["unused"])})
        self.assertIsNone(analyze_columns(unused)["categorical_summary"].iloc[0]["top"])

    def test_excel_export_does_not_create_formulas(self):
        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory() as directory:
            path = save_tables({"data": pd.DataFrame({"value": ["=1+1"]})}, Path(directory) / "f.xlsx")
            cell = load_workbook(path)["data"]["A2"]
            self.assertEqual((cell.value, cell.data_type), ("=1+1", "s"))

    def test_list_cells_and_timezone_export(self):
        df = pd.DataFrame({"tags": [[1], [2], None], "time": pd.date_range("2024", periods=3, tz="UTC")})
        tables = analyze_columns(df)
        self.assertIn("frequency_tags", tables)
        with tempfile.TemporaryDirectory() as directory:
            path = save_tables({"data": df.drop(columns="tags")}, Path(directory) / "tz.xlsx")
            self.assertEqual(len(pd.read_excel(path)), 3)


if __name__ == "__main__":
    unittest.main()
