"""Track original non-pawn pieces through actual PGN, including captures/castling.
All 16 independent questions share one PGN state in a single official SDK call.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from functools import lru_cache
import io,json,random,time,urllib.request
import chess,chess.pgn,chess.svg
import probe as P
import knight as K

DATA=P.HERE/'tracking_games.json'
PLIES=(12,36,60)
INITIAL=chess.Board()
IDENTITIES={chess.square_name(sq):{'origin':chess.square_name(sq),'colour':'white' if piece.color else 'black','kind':chess.piece_name(piece.piece_type),'symbol':piece.symbol()}
            for sq,piece in sorted(INITIAL.piece_map().items()) if piece.piece_type!=chess.PAWN}
NONE='not_on_board'


def prepare():
    ids=list(dict.fromkeys(c['game_id'].split('#')[0] for c in K.cases()));games=[]
    for game_id in ids:
        url=f'https://lichess.org/game/export/{game_id}?clocks=false&evals=false&opening=false'
        with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/x-chess-pgn'}),timeout=30) as r:game=chess.pgn.read_game(io.StringIO(r.read().decode()))
        if not game or game.errors or game.board().fen()!=chess.STARTING_FEN:raise ValueError('Invalid game export')
        games.append({'game_id':game_id,'source':url,'moves':[m.uci() for m in game.mainline_moves()]})
    DATA.write_text(json.dumps({'retrieved_at':datetime.now(timezone.utc).isoformat(),'license':'CC0','games':games},indent=2))
    print('Game lengths',[(g['game_id'],len(g['moves'])) for g in games],flush=True)


@lru_cache(maxsize=1)
def games():return json.loads(DATA.read_text())['games']


@lru_cache(maxsize=40)
def position(index,plies):
    if not 1<=index<=len(games()) or plies not in PLIES:raise ValueError('Unknown game or checkpoint')
    game=games()[index-1]
    if len(game['moves'])<plies:raise ValueError('This game ended before that checkpoint')
    board=chess.Board();at={chess.parse_square(k):k for k in IDENTITIES};san=[]
    visited={k:[k] for k in IDENTITIES};castled=set()
    for i,uci in enumerate(game['moves'][:plies]):
        move=chess.Move.from_uci(uci)
        if move not in board.legal_moves:raise ValueError('Illegal move in game')
        if i%2==0:san.append(f'{i//2+1}.')
        san.append(board.san(move))
        identity=at.pop(move.from_square,None)
        at.pop(move.to_square,None)  # captured tracked piece, if any
        if board.is_castling(move):
            rank=chess.square_rank(move.from_square);kingside=chess.square_file(move.to_square)>chess.square_file(move.from_square)
            rook_from=chess.square(7 if kingside else 0,rank);rook_to=chess.square(5 if kingside else 3,rank)
            rook_id=at.pop(rook_from);at[rook_to]=rook_id;visited[rook_id].append(chess.square_name(rook_to));castled.add(rook_id);castled.add(identity)
        if identity:at[move.to_square]=identity;visited[identity].append(chess.square_name(move.to_square))
        board.push(move)
    locations={identity:chess.square_name(square) for square,identity in at.items()}
    rows=[]
    for n,(identity,info) in enumerate(IDENTITIES.items()):
        target=locations.get(identity,NONE)
        if target!=NONE:
            piece=board.piece_at(chess.parse_square(target))
            if not piece or piece.symbol()!=info['symbol']:raise ValueError('Piece identity bookkeeping mismatch')
        rng=random.Random(index*10000+plies*100+n)
        wrong=[]
        history=[sq for sq in dict.fromkeys(visited[identity]) if sq!=target]
        if history:wrong.append(rng.choice(history))
        else:
            old=info['origin']
            if old!=target:wrong.append(old)
        occupied=[chess.square_name(sq) for sq in board.piece_map() if chess.square_name(sq)!=target and chess.square_name(sq) not in wrong]
        if occupied:wrong.append(rng.choice(sorted(occupied)))
        needed=4 if target==NONE else 3
        empty=[sq for sq in chess.SQUARE_NAMES if sq!=target and sq not in wrong]
        wrong+=rng.sample(empty,needed-len(wrong))
        if target!=NONE:wrong.append(NONE)
        rng.shuffle(wrong);options=wrong[:];options.insert((index+plies+n)%5,target)
        rows.append({**info,'id':identity,'target':target,'options':options,
                     'status':'captured' if target==NONE else 'unmoved' if len(visited[identity])==1 else 'moved',
                     'castled':identity in castled,'visited':visited[identity]})
    return {'index':index,'plies':plies,'game_id':game['game_id'],'fen':board.fen(),'pgn_moves':' '.join(san)+' *','pieces':rows}


def request_for(pos,condition):
    questions={}
    for row in pos['pieces']:
        options=row['options'][:]
        if condition=='shuffle':
            rng=random.Random(pos['index']*300+pos['plies']+chess.parse_square(row['origin']))
            original=options[:]
            while options==original:rng.shuffle(options)
        instructions=(f"After all moves in `pgn_moves`, where is the original {row['colour']} {row['kind']} that started on {row['origin']}? "
            f"Track that specific original piece, not another piece of the same type. If it has been captured, select {NONE}. "
            "The record is standard SAN from the standard initial chess position. Account for captures and castling.")
        questions[row['id']]={'type':'choice','instructions':instructions,'criteria':{a:None for a in options}}
    return {'model':P.MODEL,'state':{'pgn_moves':pos['pgn_moves']},'questions':questions}


def ask(index,plies,condition='base',*,pgn_override=None):
    if condition not in ('base','repeat','shuffle'):raise ValueError('Unknown condition')
    pos=position(index,plies);request=request_for(pos,condition)
    if pgn_override is not None:request['state']={'pgn_moves':pgn_override}
    started=time.perf_counter()
    response=P.client().system_one(model=P.MODEL,state=request['state'],questions={k:P.Choice(instructions=v['instructions'],criteria=v['criteria']) for k,v in request['questions'].items()})
    if set(response.answers)!=set(request['questions']):raise ValueError('Missing answers')
    answers=[]
    for row in pos['pieces']:
        a=response.answers[row['id']]
        if set(a.probabilities)!=set(row['options']):raise ValueError('Option mismatch')
        answers.append({**row,'pick':a.choice,'hit':a.choice==row['target'],'probabilities':dict(a.probabilities),'confidence':a.confidence})
    usage=response.usage
    return {**pos,'condition':condition,'answers':answers,'request':request,'latency_ms':round(1000*(time.perf_counter()-started)),
            'input_tokens':usage.input_tokens,'output_tokens':usage.output_tokens}


def summarize(trials):
    summary={}
    for condition in ('base','repeat','shuffle'):
        for group,values in [('plies',PLIES),('kind',('knight','bishop','rook','queen','king')),('status',('unmoved','moved','captured')),('colour',('white','black'))]:
            for value in values:
                rows=[a for t in trials if t['condition']==condition for a in t['answers'] if (t['plies'] if group=='plies' else a[group])==value]
                summary[f'{condition}/{group}/{value}']={'hit':sum(a['hit'] for a in rows),'n':len(rows)}
        rows=[a for t in trials if t['condition']==condition for a in t['answers'] if a['castled']]
        summary[f'{condition}/castled']={'hit':sum(a['hit'] for a in rows),'n':len(rows)}
    return summary


def main():
    if not DATA.exists():prepare()
    jobs=[(i,p,c) for i,g in enumerate(games(),1) for p in PLIES if len(g['moves'])>=p for c in ('base','repeat','shuffle')]
    random.Random(29822).shuffle(jobs)
    with ThreadPoolExecutor(max_workers=4) as pool:trials=[f.result() for f in as_completed([pool.submit(ask,*j) for j in jobs])]
    out={'model':P.MODEL,'created_at':datetime.now(timezone.utc).isoformat(),
         'design':'original 16 non-pawn pieces; 10 actual games, checkpoints at 12/36/60 half-moves when available; 16 independent Choice questions per call; 5 options always including not_on_board; PGN only',
         'summary':summarize(trials),'trials':trials,'requests':len(trials),'judgments':16*len(trials),
         'cost_usd':round(sum(t['input_tokens']+t['output_tokens'] for t in trials)*P.USD_PER_TOKEN,4)}
    (P.HERE/'results_tracking.json').write_text(json.dumps(out,ensure_ascii=False,indent=1))
    print(json.dumps({k:v for k,v in out.items() if k!='trials'}))

if __name__=='__main__':main()
