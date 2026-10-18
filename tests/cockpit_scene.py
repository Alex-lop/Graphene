"""One scene the cockpit tests share: a plan with a question, an agent running, one waiting for sign-off,
one that waits on those, a proposal and a finished task, in a repository of twelve files."""

from graphene_map.cockpit.model import Ev, Model, Question, Task


def scene() -> Model:
    m = Model("users come back with their ids")
    m.clock = 100.0
    m.files = [f"models/m{i}.py" for i in range(9)] + [f"db/d{i}.py" for i in range(3)]
    ids = Task("ids", "users return ids", "running", ["models/**"], agent="fox", checks=3, passed=1)
    ids.touched = {"models/m0.py": 90.0, "models/m1.py": 95.0}
    ids.stopped = [("db/ids_2.py", 96.0)]
    ids.events = [Ev(50, "read", path="tests/util.py"), Ev(60, "edit", path="models/m0.py")]
    m.tasks = {
        "ids": ids,
        "migrate": Task("migrate", "migrate old ids", "review", agent="oak", checks=2, passed=2),
        "tests": Task("tests", "tests for ids", "waiting", needs=["ids", "migrate"]),
        "docs": Task("docs", "docs for ids", "proposed"),
        "schema": Task("schema", "the schema", "done", changed=["db/schema.py", "db/m.py", "db/n.py"]),
    }
    m.questions = [Question("q", "Keep old ids working?", "keep both", ["drop old"])]
    m.selected = "ids"
    return m
