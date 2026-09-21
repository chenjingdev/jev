from copy import deepcopy

import jev_escape_verify as verify


def test_verification_requests_ignore_truth_fields():
    trial=verify.source_trials("development")[0]
    data=verify.verification_input(trial)
    changed=deepcopy(trial);changed["expected_mate"]=not trial["expected_mate"]
    for p in changed["proposals"]:
        p["true_escape"]=not p["true_escape"];p["expected_destinations"]=["fake"]
    assert verify.verification_input(changed)==data
    delta={"answers":{}}
    for i in range(len(data["proposals"])):
        delta["answers"][f"p{i}_file_delta"]={"choice":"0"};delta["answers"][f"p{i}_rank_delta"]={"choice":"1"}
    assert verify.movement_request(data,delta)==verify.movement_request(verify.verification_input(changed),delta)


def test_uniform_transform_moves_and_captures_without_legality_decision():
    state={"side_to_move":"White","pieces":[
        {"color":"White","kind":"king","square":"a1","column":1,"rank":1},
        {"color":"White","kind":"rook","square":"a2","column":1,"rank":2},
        {"color":"Black","kind":"pawn","square":"a8","column":1,"rank":8},
        {"color":"Black","kind":"king","square":"h8","column":8,"rank":8}]}
    after=verify.transformed_state(state,"a2","a8")
    assert sum(p["square"]=="a8" for p in after["pieces"])==1
    assert next(p for p in after["pieces"] if p["square"]=="a8")["kind"]=="rook"
    assert after["side_to_move"]=="Black"


def test_public_inference_has_no_reference_label(monkeypatch):
    selected = {"fen":"x", "proposals":[], "stage":{"request":{}},
                "index":None, "kind":None, "expected_mate":None}
    verified = {"verified_mate_predicted":True, "verified_escape_predicted":False,
                "verified":[], "stages":[]}
    monkeypatch.setattr(verify.chooser,"run_one",lambda case:selected)
    monkeypatch.setattr(verify,"verify_trial",lambda trial:verified)
    result=verify.infer_mate("some fen")
    assert result=={"mate":True,"escape":False,"proposals":[],"stages":[selected["stage"]]}


def test_beam_inference_chains_model_outputs_without_reference_label(monkeypatch):
    import jev_escape_beam as beam
    first={"fen":"x","proposals":[],"stage":{"request":{"first":1}},"expected_mate":None}
    refined={"fen":"x","proposals":[],"stage":{"request":{"beam":1}},"expected_mate":None}
    verified={"verified_mate_predicted":False,"verified_escape_predicted":True,"verified":[],"stages":[]}
    monkeypatch.setattr(verify.chooser,"run_one",lambda case:first)
    monkeypatch.setattr(beam,"run_one",lambda trial:refined)
    monkeypatch.setattr(verify,"verify_trial",lambda trial:verified)
    result=verify.infer_mate_beam("some fen")
    assert result["mate"] is False and result["escape"] is True
    assert result["stages"]==[first["stage"],refined["stage"]]
