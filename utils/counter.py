import os
import csv
from collections import defaultdict
from datetime import datetime

csv_files = ["data/example.csv"]
output_dir = "data/output/"

def parse_month(dtstr):
    try:
        dt = datetime.strptime(dtstr.split('.')[0], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m")
    except ValueError:
        return "Unknown"

def main():
    os.makedirs(output_dir, exist_ok=True)
    
    for csv_file in csv_files:
        counts = defaultdict(int)
        
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                month = parse_month(row.get('datetime', ''))
                counts[month] += 1
        
        output_file = os.path.join(output_dir, os.path.basename(csv_file).replace('.csv', '_counts.csv'))
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Month', 'Count'])
            for month, count in sorted(counts.items()):
                writer.writerow([month, count])
    today_str = datetime.now().strftime("%Y-%m-%d")
    lines = []
    lines.append(f"-----Log Time: {today_str} -----")
    for csv_file in csv_files:
        output_file = os.path.join(output_dir, os.path.basename(csv_file).replace('.csv', '_counts.csv'))
        lines.append(f"Processed file: {csv_file}, output saved to: {output_file}")
    for line in lines:
        print(line)
    #maybe for status countning other method or other counter anyone. 
    for (month, status), count in counts.items():
        print(f"{month} - {status}: {count}")