"""Controlled first two stages: coordinate/colour reading, then one-move win.

Same paired sparse/dense positions and choices, compact records, no descriptions.
Positions are constructed legal local sequences, not human tournament records.
"""
from __future__ import annotations
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import random
import re
import time
import engine as E
import brain
import sight
from typesafe_sdk import Choice

HERE = Path(__file__).resolve().parent
STAGES = ('identify', 'complete')
CONDITIONS = ('base', 'repeat', 'shuffle', 'rotate90', 'rotate180', 'rotate270')
QUESTIONS = {
 'occupied': 'Which candidate coordinate currently contains a stone of either colour?',
 'identify': 'Which one of the five candidate coordinates currently contains a white stone? Select that coordinate.',
 'complete': 'White to move. Which one of the five empty candidate coordinates wins immediately by completing five white stones in a row? Select that coordinate.',
}

@dataclass
class Case:
    seed: int
    stage: str
    density: str
    direction: str
    moves: list[str]
    options: list[str]
    target: str


def replay(moves, check=True):
    board=E.new_board()
    for i,at in enumerate(moves):
        r,c=E.parse_coord(at);player=E.BLACK if i%2==0 else E.WHITE
        if not E.inside(r,c) or board[r][c] or (check and E.forbidden(board,r,c,player)):
            raise ValueError(f'Invalid move {i+1}: {at}')
        board[r][c]=player
        if check and E.winner(board):raise ValueError('Position contains an earlier win')
    return board


def legal_drop(board, moves, at):
    r,c=E.parse_coord(at);player=E.BLACK if len(moves)%2==0 else E.WHITE
    if board[r][c] or E.forbidden(board,r,c,player) or E.wins_at(board,r,c,player):return False
    board[r][c]=player;moves.append(at);return True


def validate(case):
    board=replay(case.moves)
    if case.moves[0]!='h8' or len(case.moves)%2!=1:raise ValueError('Expected centre opening and white turn')
    if len(case.options)!=5 or len(set(case.options))!=5 or case.target not in case.options:raise ValueError('Invalid options')
    if case.stage=='occupied':
        hits=[at for at in case.options if board[E.parse_coord(at)[0]][E.parse_coord(at)[1]] != E.EMPTY]
    elif case.stage=='identify':
        hits=[at for at in case.options if board[E.parse_coord(at)[0]][E.parse_coord(at)[1]]==E.WHITE]
    elif case.stage=='complete':
        if any(board[r][c] for r,c in map(E.parse_coord,case.options)):raise ValueError('Completion options must be empty')
        hits=[E.coord(*p) for p in sight.winning_points(board,E.WHITE)]
    else:raise ValueError('Unknown stage')
    if hits!=[case.target]:raise ValueError('Answer does not match position')
    return board


def _pair(seed, diagonal):
    rng=random.Random(90000+seed+100000*diagonal)
    direction=(1,1) if diagonal else (0,1)
    dr,dc=direction
    line=[E.coord(7+dr*k,7+dc*k) for k in range(6)]
    target=line[5]
    # Reserve the white line, its hole and one square beyond it.
    reserved=set(line[1:])
    rr,cc=7+dr*6,7+dc*6
    if E.inside(rr,cc):reserved.add(E.coord(rr,cc))
    for attempt in range(200):
        board=E.new_board();moves=[];legal_drop(board,moves,'h8')
        okay=True
        for white in line[1:5]:
            if not legal_drop(board,moves,white):okay=False;break
            choices=[a for a in E.candidates(board,E.BLACK,cap=225,radius=1)
                     if a['id'] not in reserved and not a['wins']]
            if not choices:okay=False;break
            move=rng.choice(choices[:8])['id']
            if not legal_drop(board,moves,move):okay=False;break
        if not okay or sight.winning_points(board,E.WHITE)!=[E.parse_coord(target)]:continue
        sparse=moves[:]
        # Add 20 local moves BEFORE white completes its four; preserve all original moves.
        prefix=sparse[:5];dense_board=replay(prefix);dense=prefix[:]
        fixed=set(sparse)|reserved
        line_cells=[E.parse_coord(at) for at in line]
        for _ in range(20):
            player=E.BLACK if len(dense)%2==0 else E.WHITE
            candidates=[a for a in E.candidates(dense_board,player,cap=225,radius=1)
                        if a['id'] not in fixed and not a['wins']
                        and min(max(abs(a['r']-r),abs(a['c']-c)) for r,c in line_cells)>=2]
            if not candidates:okay=False;break
            if not legal_drop(dense_board,dense,rng.choice(candidates[:12])['id']):okay=False;break
        if not okay:continue
        for at in sparse[5:]:
            if not legal_drop(dense_board,dense,at):okay=False;break
        if not okay or sight.winning_points(dense_board,E.WHITE)!=[E.parse_coord(target)]:continue
        # Same four distractors in both densities, from near existing black stones.
        empty=[E.coord(r,c) for r in range(15) for c in range(15)
               if not board[r][c] and not dense_board[r][c] and E.coord(r,c)!=target
               and any(E.inside(r+a,c+b) and board[r+a][c+b]==E.BLACK
                       for a in (-1,0,1) for b in (-1,0,1) if a or b)]
        if len(empty)<4:continue
        completion=[target,*rng.sample(empty,4)]
        white_target=line[1+(seed%4)]
        black_points=[at for i,at in enumerate(sparse) if i%2==0]
        identify=[white_target,*rng.sample(black_points,2),*rng.sample(empty,2)]
        rng.shuffle(completion);rng.shuffle(identify)
        cases=[]
        for stage,opts,answer in [('identify',identify,white_target),('complete',completion,target)]:
            for density,history in [('sparse',sparse),('dense',dense)]:
                # Vary absolute locations/directions without changing the paired comparison.
                turns=((seed-1)//2)%4
                case=Case(seed,stage,density,'diagonal' if diagonal else 'axis',
                          [sight.rotate_coord(at,turns) for at in history],
                          [sight.rotate_coord(at,turns) for at in opts],sight.rotate_coord(answer,turns))
                validate(case);cases.append(case)
        return cases
    raise ValueError('Could not construct controlled legal pair')


@lru_cache(maxsize=64)
def cases_for_seed(seed):
    return _pair(seed, seed%2==0)


def transform(case, condition):
    turns={'rotate90':1,'rotate180':2,'rotate270':3}.get(condition,0)
    case=copy.deepcopy(case)
    case.moves=[sight.rotate_coord(at,turns) for at in case.moves]
    case.options=[sight.rotate_coord(at,turns) for at in case.options]
    case.target=sight.rotate_coord(case.target,turns)
    if condition=='shuffle':
        original=case.options[:];rng=random.Random(case.seed+781)
        while case.options==original:rng.shuffle(case.options)
    return case,turns


def ask(case, condition='base', *, instructions_override=None, state_override=None):
    if condition not in CONDITIONS:raise ValueError('Unknown condition')
    case,turns=transform(case,condition)
    board=validate(case)
    state=state_override if state_override is not None else {'game':'gomoku, 15x15','to_move':'white','moves':''.join(case.moves)}
    instructions=instructions_override if instructions_override is not None else QUESTIONS[case.stage]+' '+sight.BOARD_COMPACT
    criteria={at:None for at in case.options}
    started=time.perf_counter()
    response=brain.client().system_one(model=brain.MODEL,state=state,
        questions={'point':Choice(instructions=instructions,criteria=criteria)})
    answer=response.answers['point'];usage=getattr(response,'usage',None)
    if answer.choice not in criteria or set(answer.probabilities)!=set(criteria):raise ValueError('Response options mismatch')
    return {**asdict(case),'condition':condition,'board':board,'pick':answer.choice,
        'unrotated_pick':sight.rotate_coord(answer.choice,-turns),'hit':answer.choice==case.target,
        'probabilities':dict(answer.probabilities),'p_target':answer.probabilities[case.target],
        'latency_ms':round(1000*(time.perf_counter()-started)),
        'input_tokens':usage.input_tokens if usage else 0,'output_tokens':usage.output_tokens if usage else 0,
        'request':{'model':brain.MODEL,'state':state,'questions':{'point':{'type':'choice','instructions':instructions,'criteria':criteria}}}}


def summarize(trials):
    lookup={(t['seed'],t['stage'],t['density'],t['condition']):t for t in trials}
    summary={}
    for stage in STAGES:
        for density in ('sparse','dense'):
            for direction in ('all','axis','diagonal'):
                for condition in CONDITIONS:
                    rows=[t for t in trials if t['stage']==stage and t['density']==density and t['condition']==condition and (direction=='all' or t['direction']==direction)]
                    summary[f'{stage}/{density}/{direction}/{condition}']={
                        'hit':sum(t['hit'] for t in rows),'n':len(rows),
                        'same_as_base':sum(t['unrotated_pick']==lookup[t['seed'],stage,density,'base']['pick'] for t in rows)}
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds',type=int,default=20)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--out',default=str(HERE/'results_basics.json'))
    args=parser.parse_args()
    cases=[case for seed in range(1,args.seeds+1) for case in cases_for_seed(seed)]
    jobs=[(case,condition) for case in cases for condition in CONDITIONS]
    random.Random(20260920).shuffle(jobs)
    trials=[];checkpoint=Path(args.out).with_suffix('.jsonl')
    with checkpoint.open('w') as log,ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(ask,*job) for job in jobs]):
            row=future.result();trials.append(row);log.write(json.dumps(row)+'\n');log.flush()
            if len(trials)%80==0:print(f'{len(trials)}/{len(jobs)} complete',flush=True)
    result={'created_at':datetime.now(timezone.utc).isoformat(),'model':brain.MODEL,
        'design':'paired 9/29-stone legal constructed sequences; fixed compact format; five undescribed coordinates; target always included; 2 black + 2 empty distractors for identification; 4 empty distractors for completion; same options across density; preserved ordinal under rotation',
        'cases':[asdict(c) for c in cases],'summary':summarize(trials),'trials':trials,
        'cost_usd':round(sum(t['input_tokens']+t['output_tokens'] for t in trials)*brain.USD_PER_TOKEN,4)}
    Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=1));checkpoint.unlink()
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','trials')},ensure_ascii=False))

if __name__=='__main__':main()
