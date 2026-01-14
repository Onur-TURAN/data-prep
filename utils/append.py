import re
import itertools
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
    "xp_cmdshell", "declare ", "cast(", "convert("
]
ENCODED_PATTERNS = [
    "0x", "unhex(", "from_base64(", "to_base64("
]

SQL_FUNCTIONS = [
    "substring(", "substr(", "mid(", "left(", "right(",
    "len(", "length(", "ascii(", "chr(",
    "rand("
]

BOOLEAN_OPERATORS = [" and ", " or ", " xor ", " like ", " rlike "]

COMBOS = []
for r in [2, 3, 4]:
    for combo in itertools.product(SPECIAL_CHARS, repeat=r):
        COMBOS.append("".join(combo))


def extract_sql_features(query):
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

        # Regex tespit
        "NumStringLiteralsSingle": len(re.findall(r"'[^']*'", query)),
        "NumStringLiteralsDouble": len(re.findall(r'"[^"]*"', query)),
        "NumNumberTokens": len(re.findall(r"[0-9]+", query)),
    }

    for pattern in INJECTION_PATTERNS:
        safe = pattern.replace(" ", "_").replace("(", "").replace(")", "").replace("'", "")
        features[f"Has_{safe}"] = int(pattern in q)

    # ------------------------
    # Encoded payload 
    # ------------------------
    for enc in ENCODED_PATTERNS:
        features[f"Has_{enc.replace('(','').replace(')','')}"] = int(enc in q)


    for fn in SQL_FUNCTIONS:
        fname = fn.replace("(", "")
        features[f"HasFunc_{fname}"] = int(fn in q)

    # ------------------------
    # Boolean operator detection
    # ------------------------
    for op in BOOLEAN_OPERATORS:
        op_s = op.strip()
        features[f"HasBool_{op_s}"] = int(op in q)

    for tok in SPECIAL_CHARS:
        safe = tok.replace(" ", "SPACE").replace("'", "SQ").replace('"', "DQ")
        features[f"HasTok_{safe}"] = int(tok in query)

    for c in COMBOS:
        safe = c.replace(" ", "_").replace("'", "SQ").replace('"', "DQ")
        features[f"Combo_{safe}"] = int(c in query)

    return features


# Process the dataframe in chunks to avoid memory issues
chunk_size = 1000  # Number of rows per chunk
output_file = "data/sql_features_output.csv"

# Write header to the output file
pd.DataFrame().to_csv(output_file, index=False)

# Process each chunk and save results
for i, chunk in enumerate(pd.read_csv("data/example.csv", chunksize=chunk_size)):
    feature_df = chunk["Query"].apply(extract_sql_features).apply(pd.Series)
    output_chunk = pd.concat([chunk, feature_df], axis=1)
    output_chunk.to_csv(output_file, mode="a", header=(i == 0), index=False)
