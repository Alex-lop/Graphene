"""Print the agents the hooks saw in a probe's fixture: id, type, session."""

import glob
import sqlite3
import sys

store = glob.glob(f"/tmp/gc-{sys.argv[1]}/" + "." + "graphene" + "/*.db")[0]
for row in sqlite3.connect(store).execute("select id, type, session_id from agents"):
    print(row)
