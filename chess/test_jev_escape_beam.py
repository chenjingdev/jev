from copy import deepcopy

import jev_escape_beam as beam


def test_beam_uses_only_first_jev_probabilities_and_fixed_width():
    trial=beam.source_trials("development")[0]
    request=beam.request_for(trial)
    assert len(request["questions"])==len(trial["proposals"])
    for proposal in trial["proposals"]:
        criteria=request["questions"]["escape_"+proposal["source"]]["criteria"]
        assert "none" in criteria and len(criteria)<=beam.TOP_K+1
    changed=deepcopy(trial);changed["expected_mate"]=not trial["expected_mate"]
    for p in changed["proposals"]:
        p["true_escape"]=not p["true_escape"];p["expected_destinations"]=["fake"]
    assert beam.request_for(changed)==request
