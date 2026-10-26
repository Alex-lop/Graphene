"""Sign-offs given at once, as ⏎ pressed down the review list in graphene watch gives them (each is a process
of its own): the second waits for the first to end, so it is checked on the merge with what the first
landed. Given while the first one's check ran, it had been checked without it: two tasks red together both
landed, and ⏎ twice on one task put it back in review after it had landed."""

import threading

from test_land_moved import A, B, C, D, git
from test_review_every_merge import ALEX, parked

from graphene_map import plan
from graphene_map.plan import DONE, REVIEW
from graphene_map.store import Store


def at_once(root, monkeypatch, first, second):
    """``second`` signed off from another thread while ``first``'s check on the merge runs; the second is
    given two seconds to end before the first goes on. Returns what each was told."""
    real, other, said = plan.run_check, [], {}

    def yes(node_id, key):
        with Store.open(root) as store:
            try:
                plan.signoff(store, node_id, ALEX, checkout=root)
                said[key] = "done"
            except plan.Refused as no:
                said[key] = str(no)

    def check(command, checkout, leave_out=(), at=None, env=None):
        if not other:
            other.append(threading.Thread(target=yes, args=(second, "second")))
            other[0].start()
            other[0].join(2)
        return real(command, checkout, leave_out, at=at)

    monkeypatch.setattr(plan, "run_check", check)
    yes(first, "first")
    other[0].join()
    return said


def test_two_tasks_red_together_signed_off_at_once_never_both_land(tmp_path, monkeypatch):
    root = parked(tmp_path, monkeypatch, [A, B])
    (root / "notes.txt").write_text("mine\n")  # a commit of yours: each yes is checked on a merge
    git(root, "add", "notes.txt")
    git(root, "commit", "-qm", "mine")
    said = at_once(root, monkeypatch, "a", "b")  # b's yes while a's check runs
    assert said["first"] == "done" and "b's check" in said["second"], said
    with Store.open(root) as store:
        assert plan.get(store, "b").state == REVIEW
    assert not (root / "b.py").exists()  # nothing of b reached your checkout


def test_a_task_signed_off_twice_at_once_stays_done(tmp_path, monkeypatch):
    root = parked(tmp_path, monkeypatch, [C, D])
    with Store.open(root) as store:
        plan.signoff(store, "c", ALEX, checkout=root)  # landed: d's yes is checked on a merge
    said = at_once(root, monkeypatch, "d", "d")
    assert "done" in said.values(), said
    with Store.open(root) as store:
        assert plan.get(store, "d").state == DONE and plan.unlanded(store, "d") is None
    assert (root / "d.py").exists() and "graphene/d" not in git(root, "branch", "--list")
