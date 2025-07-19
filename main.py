import utils.line
import utils.correlation as crl



def main():
    utils.line.file_name = 'data/line.txt'
    utils.line.process_file()
    crl.csv_files = crl.ask_for_csv_file()
    crl.main()