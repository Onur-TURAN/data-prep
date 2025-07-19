import pandas as pd
import tkinter as tk
from tkinter import filedialog
import matplotlib.pyplot as plt

def ask_for_csv_file():
    root = tk.Tk()
    root.withdraw()
    file_paths = filedialog.askopenfilename(
        title="Select two CSV files",
        filetypes=[("CSV files", "*.csv")],
        multiple=True
    )
    return list(file_paths)

csv_files = ask_for_csv_file()

if len(csv_files) != 2:
    raise ValueError("Please select exactly two CSV files.")

df1 = pd.read_csv(csv_files[0])
df2 = pd.read_csv(csv_files[1])

if df1.shape[0] != df2.shape[0]:
    raise ValueError("The two CSV files must have the same number of rows.")

df1.set_index(df1.columns[0], inplace=True)
df2.set_index(df2.columns[0], inplace=True)

if df1.shape[1] < 1 or df2.shape[1] < 1:
    raise ValueError("Both CSV files must have at least two columns (including the index).")

changes = pd.DataFrame(index=df1.index)
changes['Change'] = df2.iloc[:, 0] - df1.iloc[:, 0]  # 0. sütun çünkü index sonrası ilk sütun

if not changes.empty:
    changes['Status'] = changes['Change'].apply(lambda x: 'Increase' if x >= 0 else 'Decrease')
    print(changes)
    changes['Change'].plot(kind='bar', color=changes['Change'].apply(lambda x: 'green' if x >= 0 else 'red'))
    plt.title('Changes in Second Column Values')
    plt.xlabel('Names')
    plt.ylabel('Change')
    plt.show()
else:
    print("No changes detected between the two CSV files.")