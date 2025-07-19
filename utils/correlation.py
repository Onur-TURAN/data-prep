import pandas as pd
import tkinter as tk
from tkinter import filedialog
import matplotlib.pyplot as plt 


def ask_for_csv_file():
    """Open a file dialog to select a CSV file."""
    root = tk.Tk()
    root.withdraw()  # Hide the root window
    file_path = filedialog.askopenfilename(
        title="Select a CSV file",
        filetypes=[("CSV files", "*.csv")]
        multiple=True
    )
    return list(file_paths)

csv_files = ask_for_csv_file

if len(csv_files) != 2:
    raise ValueError("Please select exactly two CSV files.")
else:
    df1 = pd.read_csv(csv_files[0])
    df2 = pd.read_csv(csv_files[1])

    if df1.shape[0] != df2.shape[0]:
        raise ValueError("The two CSV files must have the same number of rows.")
    else:
        df1.set_index(df1.columns[0], inplace=True)
        df2.set_index(df2.columns[0], inplace=True)
        changes = pd.DataFrame(index=df1.index)
        if df1.shape[1] < 2 or df2.shape[1] < 2:
            raise ValueError("Both CSV files must have at least two columns.")
        else:
            changes['change'] = df2.iloc[:, 1] - df1.iloc[:, 1]
            print(changes)
            changes['Change'].plot(kind='bar', color=changes['Change'].apply(lambda x: 'green' if x >= 0 else 'red')
        if not changes.empty:
            changes['Status'] = changes['Change'].applu(lambda x: 'Increase' if x >= 0 else 'Decrase')
            changes['Change'].plot(kind='bar', color=changes['Change'].apply(lambda x: 'green' if x >= 0 else 'red'))
            plt.title('Changes in Second Column Values')
            plt.xlabel('Names')
            plt.ylabel('Change')
            plt.show()
        else
            print("No changes detected between the two CSV files.")
