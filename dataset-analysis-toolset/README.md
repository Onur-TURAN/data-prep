# Dataset Analysis Toolset

CSV, TSV, Excel, Parquet ve JSON dosyalarını kısa, bağımsız fonksiyonlarla inceleyen bir Python araç setidir. Sonuçları konsolda tablo olarak gösterir; Excel veya HTML raporu üretir.

Python 3.10 veya daha yeni bir sürüm gerekir.

## Kurulum

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
```

## Hazır komutlar

Bir veri setindeki tüm sütunları yazdırıp seçilen sütunları analiz et:

```bash
python main.py data/customers.csv --columns age city income --output outputs/customers.xlsx
```

İki veri setindeki farklı isimli sütunları karşılaştır:

```bash
python main.py data/a.csv --dataset2 data/b.xlsx \
  --pair age=customer_age --pair city=customer_city \
  --output outputs/comparison.xlsx
```

Tekil bir anahtar üzerinden satır uyuşmazlıklarını da bul:

```bash
python main.py data/old.csv --dataset2 data/new.csv \
  --key id --row-columns status amount \
  --output outputs/row_differences.html
```

`--row-columns` verilmezse anahtar dışındaki tüm ortak sütunlar karşılaştırılır.

CSV ayracı (`,` `;` tab `|`) otomatik tahmin edilir; kodlama için sırasıyla UTF-8, Windows Türkçe (cp1254) ve Latin-1 denenir. Gerekirse elle verin:

```bash
python main.py data/excel_export.csv --sep ";" --decimal "," --encoding cp1254
```

`--pair` verilmezse iki dosyada ortak olan analiz sütunları otomatik karşılaştırılır. `--columns` da verilmezse tüm ortak sütunlar kullanılır.

## Fonksiyonları doğrudan çağırma

```python
from dataset_tools import (
    analyze_columns,
    column_table,
    compare_columns,
    compare_rows_by_key,
    compare_schema,
    load_dataset,
    print_tables,
    save_tables,
)

df1 = load_dataset("data/a.csv")
df2 = load_dataset("data/b.xlsx")

# 1) Sütun adları, veri tipleri, eksik ve benzersiz değerler
print_tables({"columns": column_table(df1)})

# 2) Seçilen sütunların analiz tabloları
tables = analyze_columns(df1, columns=["age", "city", "income"], top_n=10)
save_tables(tables, "outputs/analysis.xlsx")

# 3) İki dosyanın şeması
schema = compare_schema(df1, df2)

# 4) Aynı veya farklı isimli sütunların dağılım karşılaştırması
comparison = compare_columns(
    df1,
    df2,
    pairs=[("age", "customer_age"), ("city", "customer_city")],
)

# 5) ID bazında değişen, silinen ve eklenen satırlar
differences = compare_rows_by_key(df1, df2, key="id", columns=["status", "amount"])
```

## Üretilen analiz tabloları

- `overview`: satır/sütun, eksik hücre, tekrar satır ve bellek özeti
- `columns`: sütun adı, veri tipi, dolu/boş ve benzersiz değer sayısı
- `quality`: tamamen boş, yüksek eksik, sabit, karışık tip ve olası anahtar sütunlar
- `numeric_summary`: ortalama, standart sapma, çeyrekler ve IQR aykırı değer sayısı
- `categorical_summary`: tepe değer, sıklık, benzersizlik ve eksik oranı
- `correlation`: sayısal sütunların Pearson korelasyon matrisi
- `frequency_*`: seçilen sütunların en sık değerleri ve yüzdeleri
- `schema_comparison`: iki veri setinin sütun ve tip farkları
- `column_comparison`: ortak/yalnız değerler, Jaccard benzerliği ve sayısal ortalama farkı
- `row_mismatches`: anahtara göre eklenen, silinen veya değişen satırlar

## Test

```bash
python -m unittest discover -s tests -v
```
