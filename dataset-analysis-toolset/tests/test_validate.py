import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from dataset_tools.validate import load_rules, validate, validation_passed


class ValidateTest(unittest.TestCase):
    def test_load_rules_utf8(self):
        rules = {"columns": {"şehir": {"allowed": ["İzmir", "Ankara"]}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(load_rules(path), rules)
            path.write_text('{"columns": {"a": {"typo": true}}}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "bilinmeyen"):
                load_rules(path)
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON"):
                load_rules(path)

    def test_invalid_rules(self):
        cases = [None, [], {"unknown": {}}, {"columns": []}, {"dataset": {"oops": True}}]
        values = {"required": 1, "dtype": "integer", "allowed": "A", "pattern": "[", "unique": "yes",
                  "min": None, "max": "yesterday", "max_missing_percent": 101, "unknown": True}
        cases += [{"columns": {"x": {key: value}}} for key, value in values.items()]
        cases += [{"dataset": {key: value}} for key, value in [("min_rows", -1), ("min_rows", True),
                  ("unique_key", []), ("unique_key", "id"), ("no_duplicate_rows", 1)]]
        cases += [{"columns": {"x": {"min": 10, "max": 1}}}]
        for rules in cases:
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                validate(pd.DataFrame(), rules)

    def test_all_column_rules_and_samples(self):
        df = pd.DataFrame({"age": [None, -1, 121, "bad", 20, 30],
                           "city": ["Ankara", "Izmir", "Bursa", None, "Ankara", "Izmir"],
                           "email": ["a@b", "a@b", "oops", None, "c@d", "x@y\n"]})
        report = validate(df, {"columns": {
            "age": {"required": True, "dtype": "number", "min": 0, "max": 120},
            "city": {"allowed": ["Ankara", "Izmir"], "max_missing_percent": 10},
            "email": {"pattern": "[^@]+@[^@]+", "unique": True}}})
        counts = report.set_index(["column", "rule"])["failed_rows"]
        self.assertEqual(counts[("age", "required")], 1)
        self.assertEqual(counts[("age", "dtype")], 1)
        self.assertEqual(counts[("age", "min")], 2)
        self.assertEqual(counts[("age", "max")], 2)
        self.assertEqual(counts[("city", "allowed")], 1)
        self.assertEqual(counts[("city", "max_missing_percent")], 1)
        self.assertEqual(counts[("email", "unique")], 2)
        self.assertFalse(validation_passed(report))
        self.assertEqual(report["passed"].dtype, bool)
        samples = validate(pd.DataFrame({"a": range(10)}), {"columns": {"a": {"max": -1}}})
        self.assertEqual(samples.iloc[0]["sample_values"], "0, 1, 2, 3, 4")

    def test_nullable_categorical_and_datetime(self):
        df = pd.DataFrame({"n": pd.Series([1, None, 3], dtype="Int64"),
                           "b": pd.Series([True, None, False], dtype="boolean"),
                           "s": pd.Series(["A", None, "B"], dtype="string"),
                           "c": pd.Categorical(["A", None, "B"]),
                           "d": pd.to_datetime(["2024-01-01", None, "2024-12-31"])})
        rules = {"columns": {"n": {"dtype": "number", "min": 1, "max": 3}, "b": {"dtype": "bool"},
                             "s": {"dtype": "string", "pattern": "[AB]"},
                             "c": {"allowed": ["A", "B"], "dtype": "string", "pattern": "[AB]"},
                             "d": {"dtype": "datetime", "min": "2024-01-01", "max": "2024-12-31"}}}
        self.assertTrue(validation_passed(validate(df, rules)))
        rules["columns"]["d"]["max"] = "2024-06-01"
        self.assertEqual(validate(df, rules).iloc[-1]["failed_rows"], 1)

    def test_nulls_empty_and_missing_column(self):
        df = pd.DataFrame({"x": pd.Series([pd.NA, pd.NA], dtype="Float64")})
        rules = {"columns": {"x": {"min": 0, "max": 5, "pattern": "x", "allowed": [], "unique": True}}}
        self.assertTrue(validation_passed(validate(df, rules)))
        self.assertTrue(validation_passed(validate(df.iloc[:0], {"columns": {"x": {"max_missing_percent": 0}}})))
        self.assertTrue(validation_passed(validate(df, {})))
        report = validate(df, {"columns": {"absent": {"required": True, "min": 0}},
                               "dataset": {"unique_key": ["absent"]}})
        self.assertEqual(len(report), 1)
        self.assertEqual((report.iloc[0]["rule"], report.iloc[0]["failed_rows"]), ("exists", 1))

    def test_dataset_rules(self):
        df = pd.DataFrame({"id": [1, 1, 1, None], "part": ["a", "a", "b", "c"]})
        report = validate(df, {"dataset": {"min_rows": 5, "unique_key": ["id", "part"], "no_duplicate_rows": True}})
        self.assertEqual(report["column"].tolist(), ["<dataset>"] * 3)
        self.assertEqual(report["failed_rows"].tolist(), [1, 3, 2])
        disabled = {"columns": {"id": {"required": False, "unique": False}}, "dataset": {"no_duplicate_rows": False}}
        self.assertTrue(validation_passed(validate(df, disabled)))

    def test_fullmatch_and_mixed_dtype(self):
        df = pd.DataFrame({"x": ["abc", "abc!", None, 12]})
        report = validate(df, {"columns": {"x": {"pattern": "abc", "dtype": "string"}}})
        self.assertEqual(report["failed_rows"].tolist(), [2, 1])
        df = pd.DataFrame({"d": pd.date_range("2024-01-01", periods=2, tz="Europe/Istanbul")})
        self.assertTrue(validation_passed(validate(df, {"columns": {"d": {"min": "2023-12-31T21:00:00Z"}}})))


if __name__ == "__main__":
    unittest.main()
