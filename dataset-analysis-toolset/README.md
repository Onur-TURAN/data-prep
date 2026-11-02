# Dataset Analysis Toolset

CSV, TSV, Excel, Parquet ve JSON dosyalarını incelemek, iki dosyayı karşılaştırmak, veriyi temizlemek ve kurallara göre doğrulamak için yazılmış küçük bir Python aracı. Her işlem ayrı bir fonksiyon olduğu için ister komut satırından, ister kendi kodunuzdan çağırabilirsiniz.

Python 3.10 veya üstü gerekiyor.

## Kurulum

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## Menüden kullanım

Hiç argüman vermeden çalıştırırsanız numaralı bir menü açılır:

```bash
python main.py
```

Menü dosya yolunu, Excel'de hangi sayfanın okunacağını, hangi sütunlarla çalışılacağını ve raporun nereye kaydedileceğini adım adım sorar. Dosyayı Dosya Gezgini'nden terminale sürükleyip bırakabilirsiniz; tırnaklar kendiliğinden temizlenir. Sütun seçerken `1,3,5-7` gibi numaralar veya doğrudan sütun adları yazılabilir, boş bırakmak tüm sütunlar anlamına gelir. Bir adımda hata olursa menü kapanmaz, mesajı gösterip başa döner. Çıkmak için `0` yazın.

## Komut satırından kullanım

Komut satırı, aynı işleri betiklerde veya CI'de çalıştırmak için var.

### Analiz ve karşılaştırma

```bash
# Tek dosya: sütun listesi, kalite sorunları, özet istatistikler, frekanslar
python main.py data/customers.csv --columns age city income --output outputs/customers.xlsx

# İki dosya, farklı isimli sütunları eşleştirerek
python main.py data/a.csv --dataset2 data/b.xlsx --pair age=customer_age --pair city=customer_city

# Anahtar üzerinden eklenen, silinen ve değişen satırlar (birden çok sütun olabilir)
python main.py data/old.csv --dataset2 data/new.csv --key year month --output outputs/diff.html
```

`--pair` verilmezse iki dosyada aynı isimli sütunlar karşılaştırılır. `--row-columns` verilmezse anahtar dışındaki tüm ortak sütunlara bakılır. Excel dosyalarında sayfa seçmek için `--sheet` ve `--sheet2` kullanılır; sayfa adlarını görmek için `python main.py sheets dosya.xlsx`.

CSV ayracı (`,` `;` tab `|`) kendiliğinden tahmin edilir. Kodlama için sırayla UTF-8, Windows Türkçe (cp1254) ve Latin-1 denenir. Türkçe Excel'den alınmış, noktalı virgüllü ve virgül ondalıklı dosyalar için gerekirse elle belirtin:

```bash
python main.py data/export.csv --sep ";" --decimal "," --encoding cp1254
```

### Temizleme

```bash
python main.py clean data/raw.csv --output outputs/clean.csv --fill median --log outputs/clean_log.xlsx
```

Varsayılan olarak metinlerin baş ve sonundaki boşlukları siler, tamamen boş satır ve sütunları atar, tekrar eden satırları kaldırır ve metin olarak okunmuş sütunları gerçek tipine çevirir. Bu dönüşüm `1.234,5` gibi Türkçe sayı biçimini, `01.02.2024` ya da `2024-02-01` biçimindeki tarihleri ve evet/hayır sütunlarını kapsar. `001` gibi baştaki sıfırı anlamlı olabilecek kodlara dokunulmaz, sayıya çevrilmez.

`--fill` eksik değerler için `mean`, `median`, `mode`, `drop` ya da sabit bir değer alır. `--normalize-names` sütun adlarını `musteri_adi` biçimine getirir. Tekrar satırları tutmak için `--keep-duplicates`, tip dönüşümünü kapatmak için `--no-convert` kullanılır. Her adımda kaç satırın ve eksik hücrenin değiştiği günlüğe yazılır.

### Kurallarla doğrulama

Kurallar bir JSON dosyasında tutulur:

```json
{
  "columns": {
    "age":   {"required": true, "dtype": "number", "min": 0, "max": 120},
    "city":  {"allowed": ["Ankara", "İzmir"], "max_missing_percent": 10},
    "email": {"pattern": "^[^@]+@[^@]+$", "unique": true}
  },
  "dataset": {"min_rows": 1, "unique_key": ["id"], "no_duplicate_rows": true}
}
```

```bash
python main.py validate data/customers.csv --rules rules.json --output outputs/validation.xlsx
```

Rapor her kural için kaç satırın kuralı bozduğunu ve birkaç örnek değeri gösterir. Herhangi bir kural bozulursa komut 2 koduyla çıkar; bu sayede bir CI adımında veri bozuksa iş durdurulabilir.

### Büyük dosyalar

```bash
python main.py profile data/big.csv --chunksize 200000 --output outputs/big_profile.xlsx
```

Dosyayı belleğe tamamen almadan parça parça okur. Satır sayısını, eksik değerleri ve sayısal sütunların min, max ve ortalamasını çıkarır. Kodda `sample_dataset(df, n=100_000)` ile örneklem alınabilir. Menü de 200 bin satırı aşan dosyalarda örneklem kullanmayı önerir.

### SQL sorgu özellikleri

```bash
python main.py sql data/queries.csv --column Query --output outputs/sql_features.csv
```

Sorgu metinlerinden SQL injection sınıflandırması için sayısal özellikler çıkarır. Bunlar uzunluk, tırnak ve parantez sayıları, `union select` ve `or 1=1` gibi kalıplar, SQL fonksiyonları ve özel karakter ikilileridir. `--combo 2 3` ile üçlü kombinasyonlar da eklenebilir, ama bu yaklaşık 25 bin sütun demek.

## Kendi kodunuzdan çağırma

```python
from dataset_tools import (
    analyze_columns, clean_dataset, compare_rows_by_key,
    load_dataset, load_rules, save_dataset, save_tables, validate,
)

df = load_dataset("data/a.csv")
clean, log = clean_dataset(df, fill="median")
save_dataset(clean, "outputs/a_clean.parquet")

tables = analyze_columns(clean, columns=["age", "city"], top_n=10)
tables["validation"] = validate(clean, load_rules("rules.json"))
save_tables(tables, "outputs/report.xlsx")

diff = compare_rows_by_key(clean, load_dataset("data/b.csv"), key=["id"], columns=["status", "amount"])
```

Analiz fonksiyonlarının hepsi `pandas.DataFrame` döndürür. Bu yüzden sonuçlar `save_tables` ile tek bir Excel dosyasında ayrı sayfalar olarak ya da tek sayfalık bir HTML rapor olarak kaydedilebilir.

## Raporlardaki tablolar

| Tablo | İçerik |
|---|---|
| `overview` | Satır ve sütun sayısı, eksik hücreler, tekrar satırlar, bellek kullanımı |
| `columns` | Sütun adı, tipi, dolu/boş ve benzersiz değer sayısı |
| `quality` | Tamamen boş, çok eksik, sabit, karışık tipli ve anahtar olabilecek sütunlar |
| `numeric_summary` | Ortalama, standart sapma, çeyrekler, IQR'a göre aykırı değer sayısı |
| `categorical_summary` | En sık değer, sıklığı, benzersiz değer sayısı, eksik oranı |
| `correlation` | Sayısal sütunlar arasında Pearson korelasyonu |
| `frequency_*` | Seçilen sütunların en sık değerleri ve yüzdeleri |
| `schema_comparison` | İki dosyanın sütun ve tip farkları |
| `column_comparison` | Ortak ve yalnızca bir tarafta olan değerler, Jaccard benzerliği, ortalama farkı |
| `row_mismatches` | Anahtara göre eklenen, silinen veya değişen satırlar |
| `validation` | Kural bazında bozulan satır sayısı ve örnek değerler |

## Testler

```bash
python -m unittest discover -s tests -v
```

GitHub Actions her push'ta testleri Ubuntu ve Windows üzerinde, Python 3.10 ve 3.13 ile çalıştırır.
