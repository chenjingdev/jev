from copy import deepcopy

import jev_blocker_choice as blocker


def test_balanced_candidates_and_no_label_leak():
    rows = blocker.candidates()
    assert len(rows) == 40
    assert sum(r["clear"] for r in rows) == 20
    assert all(r["blockers"] for r in rows if not r["clear"])
    for row in rows:
        request = blocker.request_for(row)
        serialized = str(request)
        assert "clear" not in serialized and "blockers" not in serialized
        changed = deepcopy(row); changed["clear"] = not row["clear"]; changed["blockers"] = ["fake"]
        assert blocker.request_for(changed) == request
        criteria = request["questions"]["blocker"]["criteria"]
        assert "none" in criteria
        assert row["source"] not in criteria and row["target"] not in criteria
