#!/usr/bin/env python3
import os.path
import asfpy.sqlite
import sys
import yaml
import json

"""Script for migrating or initializing the DB"""

# Shortlink DB create statement if needed
DB_CREATE_STATEMENT = """
CREATE TABLE "shortlinks" (
    "id"	TEXT NOT NULL UNIQUE COLLATE NOCASE,
    "owner"	TEXT NOT NULL COLLATE NOCASE,
    "url"	TEXT NOT NULL,
    "created"	INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY("id")
);
"""


if __name__ == "__main__":
    """Run migration steps if called as main"""
    config = yaml.safe_load(open("config.yaml"))
    db = asfpy.sqlite.db(config["db"])
    if not db.table_exists("shortlinks"):
        db.runc(DB_CREATE_STATEMENT)
    assert len(sys.argv) == 2 and sys.argv[1].endswith(".json"), "Usage: migrate.py /path/to/import.json"
    json_import_file = sys.argv[1]
    assert os.path.isfile(json_import_file), f"Could not find JSON import file {json_import_file}!"
    json_data = json.load(open(json_import_file))
    print(f"Importing {len(json_data)} records...")
    for record in json_data:
        if record["id"]:
            db.upsert("shortlinks", record, id=record["id"])
    print("all done!")
