"""Jev chess diagnostics on validated Lichess CC0 positions."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from functools import lru_cache
from pathlib import Path
import json,os,random,threading,time
import chess
import chess.svg
from typesafe_sdk import TypeSafeClient,Choice

HERE=Path(__file__).resolve().parent
MODEL=os.environ.get('JEV_MODEL','jev-1.13.0')
USD_PER_TOKEN=42/1e9
LOCAL=threading.local()
STAGES=('occupied','colour','piece','mate')
QUESTIONS={
 'occupied':'Which candidate square contains a chess piece of either colour?',
 'colour':'What colour is the piece at `coordinate`?',
 'piece':'What type of chess piece is at `coordinate`, regardless of colour?',
 'mate':'Which candidate legal move checkmates the opponent immediately? Options use UCI notation: origin square followed by destination square. Select the mate-in-one move.',
}
NOTES={
 'fen':'`fen` is the current position in standard FEN: board ranks 8 to 1; uppercase pieces are white, lowercase are black; digits count empty squares. The active-colour field gives the side to move.',
 'pieces':'`pieces` maps occupied squares to piece colour and type. `turn` is the side to move. `castling` gives castling rights and `en_passant` the en-passant target or null.',
}


def client():
    if not hasattr(LOCAL,'client'):LOCAL.client=TypeSafeClient()
    return LOCAL.client


@lru_cache(maxsize=1)
def positions():return json.loads((HERE/'positions.json').read_text())['positions']


def validate_position(row):
    board=chess.Board(row['source_fen'])
    move=chess.Move.from_uci(row['opponent_move'])
    if move not in board.legal_moves:raise ValueError('Invalid source move')
    board.push(move)
    if not board.is_valid() or board.fen()!=row['fen']:raise ValueError('Incorrect puzzle starting position')
    mates=[]
    for move in list(board.legal_moves):
        board.push(move)
        if board.is_checkmate():mates.append(move.uci())
        board.pop()
    if mates!=[row['mate']]:raise ValueError('Puzzle does not have the unique expected mate')
    return board


@lru_cache(maxsize=80)
def case_for(index,stage):
    if stage not in STAGES or not 1<=index<=len(positions()):raise ValueError('Unknown case')
    row=positions()[index-1];board=validate_position(row)
    rng=random.Random(843000+index)
    case={'index':index,'stage':stage,'fen':row['fen'],'puzzle_id':row['puzzle_id']}
    if stage=='mate':
        answer=row['mate'];first=rng.choice(row['nonmate_checks'])
        wrong=[first,*rng.sample([m for m in row['distractor_pool'] if m!=first],3)]
    else:
        colour=chess.WHITE if index%2 else chess.BLACK
        occupied=[sq for sq,p in board.piece_map().items() if p.color==colour]
        if stage=='piece':
            kind=1+(index-1)%6
            matches=[sq for sq in occupied if board.piece_at(sq).piece_type==kind]
            if matches:occupied=matches
        coordinate=chess.square_name(rng.choice(sorted(occupied)))
        piece=board.piece_at(chess.parse_square(coordinate))
        if stage=='occupied':
            answer=coordinate
            wrong=rng.sample([chess.square_name(sq) for sq in chess.SQUARES if not board.piece_at(sq)],4)
        else:
            case['coordinate']=coordinate
            if stage=='colour':
                answer='white' if piece.color else 'black';wrong=['black' if piece.color else 'white']
            else:
                answer=chess.piece_name(piece.piece_type)
                wrong=rng.sample([chess.piece_name(p) for p in chess.PIECE_TYPES if p!=piece.piece_type],4)
    rng.shuffle(wrong);options=wrong[:];options.insert((index-1)%len([answer,*wrong]),answer)
    return {**case,'answer':answer,'options':options}


def state_for(case,encoding):
    board=chess.Board(case['fen'])
    if encoding=='fen':state={'fen':case['fen']}
    elif encoding=='pieces':
        state={'pieces':{chess.square_name(sq):('white' if p.color else 'black')+' '+chess.piece_name(p.piece_type)
                         for sq,p in sorted(board.piece_map().items())},
               'turn':'white' if board.turn else 'black','castling':board.castling_xfen(),
               'en_passant':chess.square_name(board.ep_square) if board.ep_square is not None else None}
    else:raise ValueError('Unknown encoding')
    if 'coordinate' in case:state['coordinate']=case['coordinate']
    return state


def ask(index,stage,encoding='fen',condition='base'):
    if condition not in ('base','repeat','shuffle'):raise ValueError('Unknown condition')
    case=case_for(index,stage);options=case['options'][:]
    if condition=='shuffle':
        original=options[:];rng=random.Random(8000+index)
        while options==original:rng.shuffle(options)
    state=state_for(case,encoding);instructions=QUESTIONS[stage]+' '+NOTES[encoding]
    criteria={at:None for at in options};started=time.perf_counter()
    response=client().system_one(model=MODEL,state=state,questions={'point':Choice(instructions=instructions,criteria=criteria)})
    a=response.answers['point'];usage=response.usage
    if set(a.probabilities)!=set(options) or a.choice not in options:raise ValueError('Answer labels mismatch')
    return {**case,'encoding':encoding,'condition':condition,'pick':a.choice,'hit':a.choice==case['answer'],
            'probabilities':dict(a.probabilities),'confidence':a.confidence,
            'latency_ms':round(1000*(time.perf_counter()-started)),
            'input_tokens':usage.input_tokens,'output_tokens':usage.output_tokens,
            'request':{'model':MODEL,'state':state,'questions':{'point':{'type':'choice','instructions':instructions,'criteria':criteria}}}}


def svg_for(row):
    board=chess.Board(row['fen']);arrows=[];squares={}
    if row['stage']=='mate':
        picked=chess.Move.from_uci(row['pick']);arrows=[chess.svg.Arrow(picked.from_square,picked.to_square,color='#16784c' if row['hit'] else '#d34242')]
    else:
        square=row.get('coordinate',row['answer']);squares={chess.parse_square(square):'#dfbe49aa'}
    return chess.svg.board(board,arrows=arrows,fill=squares,size=640,coordinates=True)


def main():
    jobs=[(i,stage,encoding,condition) for i in range(1,21) for stage in STAGES
          for encoding in ('fen','pieces') for condition in ('base','repeat','shuffle')]
    random.Random(39200).shuffle(jobs);trials=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(ask,*job) for job in jobs]):
            trials.append(f.result())
            if len(trials)%80==0:print(f'{len(trials)}/{len(jobs)} complete',flush=True)
    summary={}
    for stage in STAGES:
        for encoding in ('fen','pieces'):
            for condition in ('base','repeat','shuffle'):
                rows=[t for t in trials if t['stage']==stage and t['encoding']==encoding and t['condition']==condition]
                summary[f'{stage}/{encoding}/{condition}']={'hit':sum(t['hit'] for t in rows),'n':len(rows)}
    result={'model':MODEL,'created_at':datetime.now(timezone.utc).isoformat(),'source':'positions.json',
        'design':'20 selected Lichess mate-in-one boards; 4 tasks; FEN vs code-decoded piece map; no tactical descriptions; same options; repeat and permutation; not a chess-vs-gomoku training-data estimate',
        'summary':summary,'trials':trials,'cost_usd':round(sum(t['input_tokens']+t['output_tokens'] for t in trials)*USD_PER_TOKEN,4)}
    (HERE/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=1))
    print(json.dumps({'summary':summary,'cost_usd':result['cost_usd']}))

if __name__=='__main__':main()
