from copy import deepcopy

import jev_move_validator as validator


def test_balanced_samples_and_no_label_leak():
    for split in ("development","evaluation"):
        rows=validator.samples(split)
        assert len(rows)==40 and sum(r["expected_safe"] for r in rows)==20
        for row in rows:
            request=validator.request_for(row);serialized=str(request)
            assert "expected_safe" not in serialized and "legal_moves" not in serialized
            assert "checkmate" not in serialized.lower() and "attackers" not in serialized
            changed=deepcopy(row);changed["expected_safe"]=not row["expected_safe"]
            assert validator.request_for(changed)==request
