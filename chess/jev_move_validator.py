"""Choice validator for a concrete proposed king-saving move."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from copy import deepcopy
import argparse
import json
import random

import chess
from typesafe_sdk import Choice

import jev_attack_pipeline as pipeline
import jev_escape_choice as escape
import jev_escape_verify as verify
from jev_mate_pipeline import MOVE_RULES


OPTIONS = {
    "legal_safe": "The proposed move is legal, and after it the moving side's king is not attacked by any opponent piece.",
    "illegal_piece_move": "The source piece cannot move to that destination by its movement/capture rules, the destination has a friendly piece, or a special-move requirement is absent.",
    "blocked_path": "The movement shape is valid for a rook, bishop, or queen, but another piece lies strictly between source and destination.",
    "king_still_attacked": "The piece move is otherwise legal, but after it the moving side's king is still attacked by at least one opponent piece.",
    "uncertain": "The supplied before/after states are insufficient to choose any other option reliably.",
}


def pool(split):
    rows=[]
    run=json.loads((pipeline.HERE/f"results_jev_escape_choice_{split}.json").read_text())
    for trial in run["trials"]:
        before=trial["stage"]["request"]["state"]
        board=chess.Board(trial["fen"])
        legal={(chess.square_name(m.from_square),chess.square_name(m.to_square)) for m in board.legal_moves}
        for proposal in trial["proposals"]:
            ranked=[sq for sq,_ in sorted(proposal["probabilities"].items(),key=lambda x:x[1],reverse=True)
                    if sq not in ("none",proposal["source"])][:10]
            for destination in ranked:
                rows.append({"index":trial["index"],"fen":trial["fen"],"before":before,
                             "source":proposal["source"],"destination":destination,
                             "expected_safe":(proposal["source"],destination) in legal})
    return rows


def samples(split):
    rows=pool(split); positives=[r for r in rows if r["expected_safe"]]; negatives=[r for r in rows if not r["expected_safe"]]
    rng=random.Random(71400 if split=="development" else 71401);rng.shuffle(positives);rng.shuffle(negatives)
    return positives[:20]+negatives[:20]


def request_for(row):
    before=deepcopy(row["before"]);pieces={p["square"]:p for p in before["pieces"]};source=pieces[row["source"]]
    after=verify.transformed_state(before,row["source"],row["destination"])
    state={"game":"standard chess","moving_side":before["side_to_move"],
           "proposed_move":{"piece":pipeline.piece_text(source),"destination":row["destination"]},
           "movement_rule":MOVE_RULES[source["kind"]],"before":before,"after_uniform_coordinate_transform":after,
           "transform_note":"The after state only applies source-to-destination coordinates and captures an occupant at destination. It does not certify legality or king safety."}
    return {"model":pipeline.MODEL,"state":state,"questions":{"verdict":{"type":"choice","instructions":{
        "question":"Which option correctly classifies the proposed move? Use the complete before state for movement legality and the complete after state to determine whether every opponent piece leaves the moving side's king safe.",
        "rules":"A legal move follows the source piece rule, does not land on a friendly piece or capture a king, is not blocked when sliding, and does not leave its own king attacked."
    },"criteria":OPTIONS}}}


def run_one(row):
    request=request_for(row);q=request["questions"]["verdict"]
    response=pipeline.client().system_one(model=pipeline.MODEL,state=request["state"],questions={"verdict":Choice(instructions=q["instructions"],criteria=q["criteria"])})
    a=response.answers["verdict"]
    return {"index":row["index"],"source":row["source"],"destination":row["destination"],
            "expected_safe":row["expected_safe"],"pick":a.choice,"predicted_safe":a.choice=="legal_safe",
            "hit":(a.choice=="legal_safe")==row["expected_safe"],"probabilities":dict(a.probabilities),
            "request":request,"resolved_model":response.model,"input_tokens":response.usage.input_tokens}


def summary(rows):
    return {"hit":sum(r["hit"] for r in rows),"n":len(rows),
            "tp":sum(r["predicted_safe"] and r["expected_safe"] for r in rows),
            "fp":sum(r["predicted_safe"] and not r["expected_safe"] for r in rows),
            "tn":sum(not r["predicted_safe"] and not r["expected_safe"] for r in rows),
            "fn":sum(not r["predicted_safe"] and r["expected_safe"] for r in rows),
            "picks":{key:sum(r["pick"]==key for r in rows) for key in OPTIONS}}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--split",choices=("development","evaluation"),required=True);args=parser.parse_args()
    path=pipeline.HERE/f"results_jev_move_validator_{args.split}.json"
    if path.exists():raise SystemExit(f"Preserving existing run: {path}")
    rows=samples(args.split);random.Random(92268).shuffle(rows)
    with ThreadPoolExecutor(max_workers=4) as pool:trials=[f.result() for f in as_completed([pool.submit(run_one,row) for row in rows])]
    output={"created_at":datetime.now(timezone.utc).isoformat(),"model":pipeline.MODEL,"split":args.split,
            "design":"Balanced 20 true legal king-saving moves and 20 false top-10 Jev candidates. Labels select samples and score only; API receives the proposed move, general rule, and uniform before/after states without legal/check/attack annotations.",
            "summary":summary(trials),"requests":len(trials),"judgments":len(trials),
            "cost_usd":round(sum(t["input_tokens"] for t in trials)*42/1e9,6),"trials":trials}
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in output.items() if k!="trials"},ensure_ascii=False))


if __name__=="__main__":main()
