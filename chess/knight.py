"""Find a current white knight from actual SAN history vs current FEN."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from functools import lru_cache
import io,json,random,time,urllib.request
import chess,chess.pgn
import probe as P

DATA=P.HERE/'knight_positions.json'


def prepare():
    cases=[];games=set()
    for source in P.positions():
        game_id=source['game_url'].split('/')[3].split('#')[0]
        if game_id in games:continue
        url=f'https://lichess.org/game/export/{game_id}?clocks=false&evals=false&opening=false'
        with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/x-chess-pgn'}),timeout=30) as response:
            raw=response.read().decode()
        game=chess.pgn.read_game(io.StringIO(raw))
        if not game or game.errors or game.board().fen()!=chess.STARTING_FEN:continue
        moves=list(game.mainline_moves());board=game.board();snapshots=[];history=[];old_knight=[]
        for ply,move in enumerate(moves,1):
            if move not in board.legal_moves:raise ValueError('Illegal exported history')
            piece=board.piece_at(move.from_square)
            if piece and piece.color and piece.piece_type==chess.KNIGHT:old_knight.append(chess.square_name(move.from_square))
            board.push(move);history.append(move.uci())
            current=[sq for sq in board.pieces(chess.KNIGHT,chess.WHITE) if sq not in (chess.B1,chess.G1)]
            if current and not board.is_game_over():snapshots.append((ply,board.fen(),history[:],old_knight[:]))
        early=next((s for s in snapshots if 12<=s[0]<=20),None)
        later=next((s for s in snapshots if 36<=s[0]<=60),None)
        if not early or not later:continue
        game_number=len(games)+1
        for label,snapshot in [('short',early),('long',later)]:
            ply,fen,history,previous=snapshot;board=chess.Board(fen);rng=random.Random(83200+game_number)
            knights=set(board.pieces(chess.KNIGHT,chess.WHITE))
            target=chess.square_name(rng.choice(sorted(knights-{chess.B1,chess.G1})))
            wrong=[]
            stale=sorted({at for at in previous if not board.piece_at(chess.parse_square(at))})
            if stale:wrong.append(rng.choice(stale))
            black_knights=sorted(board.pieces(chess.KNIGHT,chess.BLACK))
            if black_knights:wrong.append(chess.square_name(rng.choice(black_knights)))
            other_white=sorted(sq for sq,p in board.piece_map().items() if p.color and p.piece_type!=chess.KNIGHT)
            if other_white:wrong.append(chess.square_name(rng.choice(other_white)))
            pool=[chess.square_name(sq) for sq in chess.SQUARES if sq not in knights and chess.square_name(sq) not in wrong]
            wrong+=rng.sample(pool,4-len(wrong));rng.shuffle(wrong)
            options=wrong[:];options.insert(len(cases)%5,target)
            replay=chess.Board();san=[]
            for i,uci in enumerate(history):
                move=chess.Move.from_uci(uci)
                if i%2==0:san.append(f'{i//2+1}.')
                san.append(replay.san(move));replay.push(move)
            cases.append({'index':len(cases)+1,'length':label,'plies':ply,'game_id':game_id,
                          'source':url,'fen':fen,'uci_history':history,'pgn_moves':' '.join(san)+' *',
                          'answer':target,'white_knights':[chess.square_name(sq) for sq in sorted(knights)],
                          'options':options,'stale_options':[at for at in options if at in stale]})
        games.add(game_id)
        if len(games)==10:break
    if len(cases)!=20:raise ValueError(f'Expected 20 positions, got {len(cases)}')
    DATA.write_text(json.dumps({'source':'Lichess public game exports; CC0 database games','retrieved_at':datetime.now(timezone.utc).isoformat(),'cases':cases},indent=2))
    print('Prepared',len(cases),'positions from',len(games),'actual games',flush=True)


@lru_cache(maxsize=1)
def cases():return json.loads(DATA.read_text())['cases']


def validate(c):
    board=chess.Board()
    for at in c['uci_history']:
        move=chess.Move.from_uci(at)
        if move not in board.legal_moves:raise ValueError('Invalid history')
        board.push(move)
    parsed=chess.pgn.read_game(io.StringIO(c['pgn_moves']))
    replay=parsed.end().board()
    if board.fen()!=c['fen'] or replay.fen()!=board.fen():raise ValueError('PGN/FEN mismatch')
    hits=[at for at in c['options'] if board.piece_at(chess.parse_square(at))==chess.Piece(chess.KNIGHT,chess.WHITE)]
    if hits!=[c['answer']] or len(set(c['options']))!=5:raise ValueError('Not a unique white knight choice')
    return board


def ask(index,encoding='pgn',condition='base'):
    if not 1<=index<=20 or condition not in ('base','repeat','shuffle'):raise ValueError('Unknown case')
    c=cases()[index-1];board=validate(c);options=c['options'][:]
    if condition=='shuffle':
        rng=random.Random(319+index)
        while options==c['options']:rng.shuffle(options)
    question='Which candidate square currently contains a white knight? Select the square after all recorded moves, not a square the knight occupied earlier.'
    if encoding=='pgn':
        state={'pgn_moves':c['pgn_moves']}
        instructions=question+' `pgn_moves` is standard SAN movetext played from the standard initial chess position; N denotes a knight.'
    elif encoding=='fen':
        state={'fen':c['fen']};instructions=question+' '+P.NOTES['fen']
    else:raise ValueError('White-knight task supports FEN or PGN')
    criteria={at:None for at in options};started=time.perf_counter()
    response=P.client().system_one(model=P.MODEL,state=state,questions={'point':P.Choice(instructions=instructions,criteria=criteria)})
    a=response.answers['point'];usage=response.usage
    if set(a.probabilities)!=set(options):raise ValueError('Response options mismatch')
    return {**c,'stage':'white_knight','encoding':encoding,'condition':condition,'pick':a.choice,
            'hit':a.choice==c['answer'],'picked_stale':a.choice in c['stale_options'],
            'probabilities':dict(a.probabilities),'confidence':a.confidence,
            'latency_ms':round(1000*(time.perf_counter()-started)),
            'input_tokens':usage.input_tokens,'output_tokens':usage.output_tokens,
            'request':{'model':P.MODEL,'state':state,'questions':{'point':{'type':'choice','instructions':instructions,'criteria':criteria}}}}


def main():
    if not DATA.exists():prepare()
    jobs=[(i,e,c) for i in range(1,21) for e in ('fen','pgn') for c in ('base','repeat','shuffle')]
    random.Random(96200).shuffle(jobs)
    with ThreadPoolExecutor(max_workers=4) as pool:trials=[f.result() for f in as_completed([pool.submit(ask,*job) for job in jobs])]
    summary={}
    for e in ('fen','pgn'):
        for length in ('short','long','all'):
            for condition in ('base','repeat','shuffle'):
                rows=[t for t in trials if t['encoding']==e and t['condition']==condition and (length=='all' or t['length']==length)]
                summary[f'{e}/{length}/{condition}']={'hit':sum(t['hit'] for t in rows),'n':len(rows),'picked_stale':sum(t['picked_stale'] for t in rows)}
    result={'model':P.MODEL,'created_at':datetime.now(timezone.utc).isoformat(),'design':'10 actual games, paired early/later positions; same five squares for FEN vs full SAN history; one white knight among options; 120 requests, not 120 independent games',
            'summary':summary,'trials':trials,'cost_usd':round(sum(t['input_tokens']+t['output_tokens'] for t in trials)*P.USD_PER_TOKEN,4)}
    (P.HERE/'results_knight.json').write_text(json.dumps(result,ensure_ascii=False,indent=1))
    print(json.dumps({'summary':summary,'cost_usd':result['cost_usd']}))

if __name__=='__main__':main()
