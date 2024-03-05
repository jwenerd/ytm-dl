#
import subprocess
import csv
from io import StringIO
from collections import Counter


# def history_stats():
hash_cmd='git log --since="1 day ago" --pretty=format:%h origin/main-output -- ./output/history.csv | tail -1'
output = subprocess.check_output([f"git diff $({hash_cmd})^ output/history.csv | grep '^+' | tail -n +2 | cut -c2-"], shell=True).decode().strip()

reader = csv.reader(StringIO(output))
rows = [row for row in reader]
#
count_at_index = lambda i: dict(Counter([row[i] for row in rows]))

songs = count_at_index(0)
artists = count_at_index(1)
album = count_at_index(2)

songs, artists, albums = [{k: v for k, v in counts if v > 1} for counts in [count_at_index(i).items() for i in range(0,3)]]
