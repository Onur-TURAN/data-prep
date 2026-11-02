import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from dataset_tools.large import profile_csv_in_chunks, sample_dataset


class LargeTest(unittest.TestCase):
    def test_sample_reproducible(self):
        df = pd.DataFrame({"x": range(20)})
        pd.testing.assert_frame_equal(sample_dataset(df, n=5), sample_dataset(df, n=5))
        self.assertEqual(len(sample_dataset(df, frac=0.25)), 5)
        self.assertIs(sample_dataset(df, n=20), df)
        self.assertIs(sample_dataset(df, n=30), df)
        self.assertEqual(len(sample_dataset(df, n=0)), 0)
        self.assertEqual(len(sample_dataset(df, frac=0)), 0)
        self.assertIs(sample_dataset(df.iloc[:0], n=0).empty, True)

    def test_invalid_sample_arguments(self):
        cases = [{}, {"n": 1, "frac": 0.5}, {"n": -1}, {"n": 1.5}, {"n": True},
                 {"frac": -0.1}, {"frac": 1.1}, {"frac": float("nan")}, {"frac": True}, {"frac": "0.5"}]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                sample_dataset(pd.DataFrame({"x": [1]}), **kwargs)

    def test_incremental_statistics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text("x;y;label\n1;10;a\n2;;b\n;30;c\n4;40;d\n100;50;e\n", encoding="utf-8")
            original = pd.read_csv
            with patch("dataset_tools.large.pd.read_csv", wraps=original) as read:
                tables = profile_csv_in_chunks(path, chunksize=2)
                self.assertEqual(read.call_args.kwargs["chunksize"], 2)
            self.assertEqual(dict(tables["overview"].itertuples(index=False, name=None)),
                             {"rows": 5, "columns": 3, "chunks": 3, "missing_cells": 2})
            columns = tables["columns"].set_index("column")
            self.assertEqual(columns.loc["x", "mean"], 107 / 4)
            self.assertEqual(columns.loc["x", "null_percent"], 20)
            self.assertEqual(columns.loc["x", "non_null"], 4)
            self.assertEqual(columns.loc["y", "mean"], 130 / 4)
            self.assertEqual(columns.loc["x", "min"], 1)
            self.assertEqual(columns.loc["x", "max"], 100)
            self.assertIsNone(columns.loc["label", "mean"])

    def test_mixed_chunks_and_all_null(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mixed.csv"
            path.write_text("mixed,reverse,empty\n1,text,\n2,word,\ntext,1,\n4,2,\n", encoding="utf-8")
            columns = profile_csv_in_chunks(path, chunksize=2)["columns"].set_index("column")
            for column in ["mixed", "reverse", "empty"]:
                for metric in ["min", "max", "mean"]:
                    self.assertIsNone(columns.loc[column, metric])
            self.assertEqual(columns.loc["empty", "null"], 4)

    def test_encoding_decimal_and_single_column(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tr.csv"
            path.write_text("şehir;tutar\nİzmir;1,5\nAnkara;2,5\n", encoding="cp1254")
            columns = profile_csv_in_chunks(path, chunksize=1, decimal=",")["columns"].set_index("column")
            self.assertEqual(columns.loc["tutar", "mean"], 2)
            explicit = profile_csv_in_chunks(path, sep=";", encoding="cp1254", decimal=",")
            self.assertEqual(explicit["columns"].iloc[1]["min"], 1.5)
            path.write_text("value\n1\n3\n", encoding="utf-8")
            self.assertEqual(profile_csv_in_chunks(path, chunksize=1)["columns"].iloc[0]["mean"], 2)

    def test_empty_header_and_invalid_chunk_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.csv"
            path.write_text("a,b\n", encoding="utf-8")
            tables = profile_csv_in_chunks(path)
            self.assertEqual(tables["overview"]["value"].tolist(), [0, 2, 0, 0])
            self.assertEqual(tables["columns"]["null_percent"].tolist(), [0, 0])
            for size in [0, -1, True, 1.5]:
                with self.subTest(size=size), self.assertRaises(ValueError):
                    profile_csv_in_chunks(path, chunksize=size)

    def test_large_integer_sum_and_null_first_chunk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integer.csv"
            value = 2**62
            path.write_text(f"id,n\n1,\n2,\n3,{value}\n4,{value}\n", encoding="utf-8")
            columns = profile_csv_in_chunks(path, chunksize=2)["columns"].set_index("column")
            self.assertEqual(columns.loc["n", "mean"], value)
            self.assertEqual(columns.loc["n", "non_null"], 2)

    def test_late_decoding_failure_restarts_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "late.csv"
            path.write_bytes(b"id,name\n" + b"1,Ankara\n" * 40_000 + "2,İzmir\n".encode("cp1254"))
            tables = profile_csv_in_chunks(path, chunksize=10_000)
            overview = dict(tables["overview"].itertuples(index=False, name=None))
            self.assertEqual(overview["rows"], 40_001)
            self.assertEqual(overview["chunks"], 5)
            self.assertEqual(tables["columns"].iloc[0]["mean"], 40_002 / 40_001)


if __name__ == "__main__":
    unittest.main()
