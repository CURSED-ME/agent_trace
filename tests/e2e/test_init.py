import atexit
import os

import agenttrace.auto
from agenttrace.decorators import track_tool

atexit.unregister(agenttrace.auto._run_server)


@track_tool(name="test_tool")
def do_something():
    print("Doing something!")
    return "done"


print(f"CWD: {os.getcwd()}")
do_something()
print("Check for DB now.")
import agenttrace.storage

print(f"DB Path is: {agenttrace.storage.DB_PATH}")
import os

print(f"File exists? {os.path.exists(agenttrace.storage.DB_PATH)}")
