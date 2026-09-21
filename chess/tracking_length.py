"""Matched games plus same-position intervention: prepend 24 reversible plies.

Knights return to their original squares, preserving piece identities, rights,
side to move and final board. Fullmove numbers shift by 12. Draws are not claimed;
assert no automatic game-over position is played past.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from functools import lru_cache
import json,random
import chess,chess.pgn
import tracking as T

CYCLES=(
 'g1f3 g8f6 b1c3 b8c6 f3g1 f6g8 c3b1 c6b8',
 'b1c3 b8c6 g1f3 g8f6 c3b1 c6b8 f3g1 f6g8',
)


@lru_cache(maxsize=32)
def extended(index,plies):
    rng=random.Random(index+99300)
    prefix=[uci for _ in range(3) for uci in rng.choice(CYCLES).split()]
    history=prefix+T.games()[index-1]['moves'][:plies]
    board=chess.Board();text=[]
    for i,uci in enumerate(history):
        if board.is_game_over(claim_draw=False):raise ValueError('Cannot continue automatically terminated game')
        move=chess.Move.from_uci(uci)
        if move not in board.legal_moves:raise ValueError('Illegal extended sequence')
        if i%2==0:text.append(f'{i//2+1}.')
        text.append(board.san(move));board.push(move)
        if i==23:
            if board.board_fen()!=chess.Board().board_fen() or board.turn!=chess.WHITE or board.castling_rights!=chess.Board().castling_rights:
                raise ValueError('Prefix failed to restore initial position')
    expected=chess.Board(T.position(index,plies)['fen'])
    if board.fen().split()[:5]!=expected.fen().split()[:5]:raise ValueError('Changed final state other than move number')
    return {'pgn_moves':' '.join(text)+' *','uci_history':history,'final_fen':board.fen(),'extra_plies':24}


def ask(index,plies,arm,repeat):
    extra=extended(index,plies) if arm=='longer' else None
    # Identical option ordering across arms and repeats; isolate added history.
    result=T.ask(index,plies,'base',pgn_override=extra['pgn_moves'] if extra else None)
    return {**result,'arm':arm,'repeat':repeat,'input_plies':plies+(24 if extra else 0)}


def main():
    earlier=json.loads((T.P.HERE/'results_tracking.json').read_text())
    ids=[i for i,g in enumerate(T.games(),1) if len(g['moves'])>=60]
    matched={}
    for condition in ('base','repeat','shuffle'):
        for plies in T.PLIES:
            rows=[a for t in earlier['trials'] if t['index'] in ids and t['plies']==plies and t['condition']==condition for a in t['answers']]
            matched[f'{condition}/{plies}']={'hit':sum(a['hit'] for a in rows),'n':len(rows)}
    jobs=[(i,p,arm,r) for i in ids for p in T.PLIES for arm in ('original','longer') for r in range(1,4)]
    for i in ids:
        for p in T.PLIES:extended(i,p)
    random.Random(74400).shuffle(jobs)
    with ThreadPoolExecutor(max_workers=4) as pool:trials=[f.result() for f in as_completed([pool.submit(ask,*j) for j in jobs])]
    lookup={(t['index'],t['plies'],t['arm'],t['repeat']):t for t in trials}
    summary={}
    for plies in T.PLIES:
        for arm in ('original','longer'):
            rows=[a for t in trials if t['plies']==plies and t['arm']==arm for a in t['answers']]
            summary[f'{plies}/{arm}']={'hit':sum(a['hit'] for a in rows),'n':len(rows),
                'per_repeat':[sum(a['hit'] for t in trials if t['plies']==plies and t['arm']==arm and t['repeat']==r for a in t['answers']) for r in range(1,4)]}
    transitions={'correct_to_wrong':0,'wrong_to_correct':0,'same_pick':0,'n':0}
    for i in ids:
        for p in T.PLIES:
            for r in range(1,4):
                a=lookup[i,p,'original',r]['answers'];b=lookup[i,p,'longer',r]['answers']
                for left,right in zip(a,b):
                    assert left['id']==right['id'] and left['target']==right['target'] and left['options']==right['options']
                    transitions['correct_to_wrong']+=left['hit'] and not right['hit']
                    transitions['wrong_to_correct']+=not left['hit'] and right['hit']
                    transitions['same_pick']+=left['pick']==right['pick'];transitions['n']+=1
    out={'created_at':datetime.now(timezone.utc).isoformat(),'model':T.P.MODEL,'game_indices':ids,
        'design':'same 5 games; original PGN vs 24 reversible knight plies prefixed, same final position/identities/questions/options; 3 repeats per arm; no independent-game claim',
        'matched_existing_results':matched,'summary':summary,'transitions':transitions,
        'prefix_cases':[{'index':i,'plies':p,**extended(i,p)} for i in ids for p in T.PLIES],
        'trials':trials,'requests':len(trials),'judgments':len(trials)*16,
        'cost_usd':round(sum(t['input_tokens']+t['output_tokens'] for t in trials)*T.P.USD_PER_TOKEN,4)}
    (T.P.HERE/'results_tracking_length.json').write_text(json.dumps(out,ensure_ascii=False,indent=1))
    print(json.dumps({k:v for k,v in out.items() if k not in ('trials','prefix_cases')}))

if __name__=='__main__':main()
