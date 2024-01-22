import csv

def find_start_index(csv_file, new_ids):
  existing_ids = get_existing_ids(csv_file)
  for index, new_id in enumerate(new_ids):

    if new_id == existing_ids[0]:
      next_in_existing = existing_ids[0:10]
      next_in_new = new_ids[index:]
      if len(next_in_new) > 10:
        next_in_new = next_in_new[0:10]
      if len(next_in_new) < 10:
        next_in_existing = next_in_existing[0:len(next_in_new)]

      if next_in_new == next_in_existing:
        return index

      difference = set(next_in_new) - set(next_in_existing)
      if len(difference) <= 2:
        # close enough match - could have had removals from
        #  playlist or whatever
        return index

  return None

def get_existing_ids(csv_file):
  existing_ids = []
  with open(csv_file, 'r') as f:
    for row in csv.reader(f, delimiter=','):
        existing_ids.append(row[len(row)-1])
        if len(existing_ids) > 200:
          break
    existing_ids.pop(0) # remove the header
  return existing_ids

def new_rows_for_file(csv_file, new_rows):
  new_ids = [new[len(new)-1] for new in new_rows]
  start_index = find_start_index(csv_file, new_ids)
  if start_index is not None:
    return new_rows[0:start_index]
  return []
