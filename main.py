import utils.line
import utils.correlation as crl
import utils.append as append
import utils.counter as counter




def main():
    utils.line.file_name = 'data/line.txt'
    utils.line.process_file()
    crl.csv_files = crl.ask_for_csv_file()
    crl.main()
    counter.csv_files = counter.ask_for_csv_file() # change to ask for csv files
    counter.main()