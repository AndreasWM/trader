import csv
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.stock_util import StockUtil

OUTPUT_FILE = 'watchlist_import.txt'

def transform(input_file, output_file):
    with open(input_file, newline='', encoding='utf-8') as f_in, \
         open(output_file, 'w', encoding='utf-8') as f_out:
        reader = csv.DictReader(f_in)
        for row in reader:
            symbol = row['Symbol'].strip()
            exchange = row['Exchange'].strip()
            f_out.write(f"{exchange}:{symbol}\n")

if __name__ == '__main__':
    util = StockUtil()
    input_file = util.get_latest_watchlist_file()
    output_file = util.get_output_file(filename=OUTPUT_FILE)
    transform(input_file, output_file)
    print(f"Fertig! Ergebnis steht in '{output_file}'.")