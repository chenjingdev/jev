"""Refine per-piece escape candidates using Jev's own top-k Choice probabilities."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import json
import random

from typesafe_sdk import Choice

import jev_attack_pipeline as pipeline
import jev_escape_choice as first


TOP_K = 10  # Selected on the development split; must stay fixed for evaluation.


def source_trials(split):
    return json.loads((pipeline.HERE / f"results_jev_escape_choice_{split}.json").read_text())["trials"]


def request_for(trial):
    state = trial["stage"]["request"]["state"]
    pieces = {p["square"]:p for p in state["pieces"]}; questions={}
    for proposal in trial["proposals"]:
        ranked=[square for square,_ in sorted(proposal["probabilities"].items(),key=lambda item:item[1],reverse=True)
                if square not in ("none",proposal["source"])][:TOP_K]
        criteria={square:first.SQUARE_CRITERIA[square] for square in ranked};criteria["none"]=first.SQUARE_CRITERIA["none"]
        piece=pieces[proposal["source"]]
        questions["escape_"+proposal["source"]]={"type":"choice","instructions":{
            "piece":pipeline.piece_text(piece),"movement_rule":pipeline.RULES[piece["kind"]],
            "candidate_origin":"The square options are the earlier Jev judgment's top candidates. They are not engine-verified legal moves.",
            "question":f"Which candidate can this exact piece legally move to now so that, after the move, the {state['side_to_move']} king is not attacked by any opponent piece? Choose none only if none works. Consider captures, occupied squares, blockers, pins, and attacks after the move."
        },"criteria":criteria}
    return {"model":pipeline.MODEL,"state":state,"questions":questions}


def run_one(trial):
    request=request_for(trial)
    started=__import__('time').perf_counter()
    response=pipeline.client().system_one(model=pipeline.MODEL,state=request["state"],questions={
        key:Choice(instructions=value["instructions"],criteria=value["criteria"]) for key,value in request["questions"].items()})
    proposals=[]
    for key,answer in response.answers.items():
        proposals.append({"source":key.removeprefix("escape_"),"destination":answer.choice,
                          "confidence":answer.confidence,"probabilities":dict(answer.probabilities)})
    stage={"request":request,"answers":{key:{"choice":a.choice,"probabilities":dict(a.probabilities),"confidence":a.confidence} for key,a in response.answers.items()},
           "resolved_model":response.model,"input_tokens":response.usage.input_tokens,"output_tokens":response.usage.output_tokens,
           "latency_ms":round(1000*(__import__('time').perf_counter()-started))}
    return {"index":trial.get("index"),"kind":trial.get("kind"),"fen":trial["fen"],
            "expected_mate":trial.get("expected_mate"),"proposals":proposals,"stage":stage}


def score(trial):
    return first.score(trial)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--split",choices=("development","evaluation"),required=True);args=parser.parse_args()
    path=pipeline.HERE/f"results_jev_escape_beam_{args.split}.json"
    if path.exists():raise SystemExit(f"Preserving existing run: {path}")
    rows=source_trials(args.split);random.Random(92267).shuffle(rows)
    with ThreadPoolExecutor(max_workers=4) as pool:
        trials=[score(f.result()) for f in as_completed([pool.submit(run_one,row) for row in rows])]
    stages=[t["stage"] for t in trials]
    output={"created_at":datetime.now(timezone.utc).isoformat(),"model":pipeline.MODEL,"split":args.split,"top_k":TOP_K,
            "design":"Second Choice per piece over the first Jev Choice's top-10 non-none destinations plus none. Candidates are selected only by Jev probabilities; no engine legal list or derived fact enters requests. K=10 was selected on development and is fixed for evaluation.",
            "summary":first.summary(trials),"requests":len(stages),"judgments":sum(len(s["answers"]) for s in stages),
            "input_tokens":sum(s["input_tokens"] for s in stages),"cost_usd":round(sum(s["input_tokens"] for s in stages)*42/1e9,6),
            "trials":sorted(trials,key=lambda t:(t["index"],t["kind"]))}
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in output.items() if k!="trials"},ensure_ascii=False))


if __name__=="__main__":main()
