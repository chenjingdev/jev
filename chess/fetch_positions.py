"""Extract a bounded sample from Lichess CC0 puzzle CSV without saving the archive.
Requires Python 3.14 compression.zstd. Selected rows are checked with python-chess.
"""
from compression import zstd
import csv,io,json,urllib.request
from datetime import datetime,timezone
from pathlib import Path
import chess

URL='https://database.lichess.org/lichess_db_puzzle.csv.zst'


def mates(board):
    result=[]
    for move in list(board.legal_moves):
        board.push(move)
        if board.is_checkmate():result.append(move)
        board.pop()
    return result


def main():
    selected=[];counts={True:0,False:0}
    with urllib.request.urlopen(URL,timeout=45) as response:
        with zstd.ZstdFile(response) as compressed:
            reader=csv.DictReader(io.TextIOWrapper(compressed,encoding='utf-8'))
            for scanned,row in enumerate(reader,1):
                if scanned>100000:raise RuntimeError('No balanced sample within scan limit')
                if 'mateIn1' not in row['Themes'].split():continue
                moves=row['Moves'].split()
                if len(moves)!=2:continue
                board=chess.Board(row['FEN'])
                if not board.is_valid():continue
                first=chess.Move.from_uci(moves[0])
                if first not in board.legal_moves:continue
                board.push(first)
                if not board.is_valid() or counts[board.turn]>=10:continue
                answers=mates(board)
                if len(answers)!=1 or answers[0].uci()!=moves[1] or answers[0].promotion:continue
                answer=answers[0]
                wrong=[m for m in board.legal_moves if m!=answer and m.from_square==answer.from_square and not m.promotion]
                checks=[m for m in wrong if board.gives_check(m)]
                if len(wrong)<4 or not checks:continue
                if any(p['fen']==board.fen() for p in selected):continue
                selected.append({'puzzle_id':row['PuzzleId'],'source_fen':row['FEN'],
                    'opponent_move':moves[0],'fen':board.fen(),'mate':answer.uci(),
                    'distractor_pool':[m.uci() for m in wrong],'nonmate_checks':[m.uci() for m in checks],
                    'rating':int(row['Rating']),'game_url':row['GameUrl']})
                counts[board.turn]+=1
                if len(selected)==20:break
    out={'source':URL,'license':'CC0','retrieved_at':datetime.now(timezone.utc).isoformat(),
         'selection':'first 10 unique-mate-in-one positions per side with >=4 nonmating legal alternatives from same piece, including a nonmating check; not representative random sample',
         'rows_scanned':scanned,'positions':selected}
    Path(__file__).with_name('positions.json').write_text(json.dumps(out,indent=2))
    print('Selected',len(selected),'from',scanned,'rows; sides',counts)

if __name__=='__main__':main()
