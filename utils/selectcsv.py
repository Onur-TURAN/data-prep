import os
from typing import List

def find_csv_in_data_dirs(root: str) -> List[str]:
    matches = []
    for dirpath, dirnames, filenames in os.walk(root):
        parts = [p.lower() for p in dirpath.replace("\\", "/").split("/")
                 if "data" in parts:
                    for f in filenames:
                        if f.lower()]