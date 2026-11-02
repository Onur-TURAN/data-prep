"""SQL injection tespiti için sorgu metinlerinden sayısal özellikler çıkarır."""

import itertools
import re
from functools import lru_cache

import pandas as pd

SPECIAL_CHARS = list(" '\"=()%;#,*+!@^&/\\|<>?:.-[]{}")

INJECTION_PATTERNS = [
    "or 1=1", "or '1'='1'", "or \"1\"=\"1\"",
    "' or '", "\" or \"", "') or ('",
    "and 1=1", "and '1'='1'",
    "union select", "union all select",
    "sleep(", "pg_sleep(", "benchmark(",
    "extractvalue(", "updatexml(",
    "load_file(", "into outfile",
    "information_schema", "table_schema",
    "group_concat(", "concat(",
    "@@version", "@@hostname", "@@datadir",
    "xp_cmdshell", "declare ", "cast(", "convert(",
]
ENCODED_PATTERNS = ["0x", "unhex(", "from_base64(", "to_base64("]
SQL_FUNCTIONS = ["substring(", "substr(", "mid(", "left(", "right(", "len(", "length(", "ascii(", "chr(", "rand("]
BOOLEAN_OPERATORS = [" and ", " or ", " xor ", " like ", " rlike "]


@lru_cache
def special_combos(lengths: tuple[int, ...] = (2,)) -> tuple[str, ...]:
    """Özel karakter kombinasyonları; 3 ve 4 uzunluk yüz binlerce sütun üretir, bilinçli açılmalı."""
    if any(r not in (2, 3, 4) for r in lengths):
        raise ValueError(f"Kombinasyon uzunlukları 2, 3 veya 4 olmalı: {list(lengths)}")
    return tuple("".join(combo) for r in lengths for combo in itertools.product(SPECIAL_CHARS, repeat=r))


def _safe(text: str) -> str:
    return text.replace(" ", "_").replace("'", "SQ").replace('"', "DQ").replace("(", "").replace(")", "")


def extract_sql_features(query: str, combo_lengths: tuple[int, ...] = (2,)) -> dict[str, int]:
    """Tek bir sorgu için uzunluk, karakter, kalıp, fonksiyon ve token özelliklerini döndürür."""
    query = "" if pd.isna(query) else str(query)
    q = query.lower()
    features = {
        "Length": len(query),
        "NumDigits": sum(ch.isdigit() for ch in query),
        "NumLetters": sum(ch.isalpha() for ch in query),
        "NumUpper": sum(ch.isupper() for ch in query),
        "NumLower": sum(ch.islower() for ch in query),
        "NumSpecial": sum(not ch.isalnum() and not ch.isspace() for ch in query),
        "NumSingleQuotes": query.count("'"),
        "NumDoubleQuotes": query.count('"'),
        "NumEqual": query.count("="),
        "NumParenOpen": query.count("("),
        "NumParenClose": query.count(")"),
        "ParenImbalance": abs(query.count("(") - query.count(")")),
        "NumStringLiteralsSingle": len(re.findall(r"'[^']*'", query)),
        "NumStringLiteralsDouble": len(re.findall(r'"[^"]*"', query)),
        "NumNumberTokens": len(re.findall(r"[0-9]+", query)),
    }
    features |= {f"Has_{_safe(p)}": int(p in q) for p in INJECTION_PATTERNS + ENCODED_PATTERNS}
    features |= {f"HasFunc_{fn[:-1]}": int(fn in q) for fn in SQL_FUNCTIONS}
    features |= {f"HasBool_{op.strip()}": int(op in q) for op in BOOLEAN_OPERATORS}
    features |= {f"HasTok_{_safe(tok) if tok not in '()' else tok}": int(tok in query) for tok in SPECIAL_CHARS}
    features |= {f"Combo_{_safe(c) if '(' not in c and ')' not in c else c}": int(c in query) for c in special_combos(tuple(combo_lengths))}
    return features


def add_sql_features(df: pd.DataFrame, column: str = "Query", combo_lengths: tuple[int, ...] = (2,)) -> pd.DataFrame:
    """Veri setine seçili sorgu sütunundan çıkarılan özellik sütunlarını ekler."""
    if column not in df:
        raise KeyError(f"Sorgu sütunu bulunamadı: {column}")
    features = pd.DataFrame([extract_sql_features(q, combo_lengths) for q in df[column]], index=df.index)
    return pd.concat([df, features], axis=1)
