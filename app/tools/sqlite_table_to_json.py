import json
import sqlite3

table_name = "note"

database_path = "../notes.db"

conn = sqlite3.connect(database_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("fetching all rows...")
cursor.execute("select * from note;")  # noqa

res = cursor.fetchall()

output = []
for row in res:
    output.append(dict(row))

with open(f"./{table_name}.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=4)
print(f"json file saved to ./{table_name}.json")