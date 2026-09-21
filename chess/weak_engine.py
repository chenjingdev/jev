"""Deliberately weak, transparent base engine: material + small piece-square terms, depth-2 negamax.

It exists so that a gut-check selector has room to help. Stockfish at 5,000 nodes
already removes most tactical blunders before a selector sees the shortlist; this
engine does not. It is deterministic (ties broken by UCI string) so the base #1 is
reproducible. Scores are in its own centipawn-like units, not Stockfish's scale.
"""
from __future__ import annotations
import chess

MATE = 100000
# Draw claims (fifty-move / threefold) are checked only up to this ply inside the search: python-chess
# replays the move stack for repetition checks, which dominated search time (depth 3: 4.4s -> 0.2s).
# Depth-1/2 arms recorded before 2026-09-21 23:00 used the check at every ply.
DRAW_CHECK_MAX_PLY = 1
VALUE = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}
# Distance-from-centre bonus for minor pieces and advancement bonus for pawns, from White's view.
CENTRE = [max(abs(chess.square_file(s) - 3.5), abs(chess.square_rank(s) - 3.5)) for s in chess.SQUARES]


def evaluate(board: chess.Board) -> int:
    """Static score from the side-to-move point of view."""
    score = 0
    for square, piece in board.piece_map().items():
        value = VALUE[piece.piece_type]
        if piece.piece_type in (chess.KNIGHT, chess.BISHOP):
            value += int(10 * (3.5 - CENTRE[square]))
        elif piece.piece_type == chess.PAWN:
            rank = chess.square_rank(square)
            value += 5 * (rank - 1 if piece.color else 6 - rank)
        score += value if piece.color == board.turn else -value
    return score


def negamax(board: chess.Board, depth: int, alpha: int, beta: int, ply: int) -> int:
    if board.is_checkmate():
        return -MATE + ply
    if board.is_stalemate() or board.is_insufficient_material():
        return 0
    if ply <= DRAW_CHECK_MAX_PLY and board.can_claim_draw():
        return 0
    if depth == 0:
        return evaluate(board)
    best = -MATE - 1
    # Captures first for alpha-beta efficiency; deterministic UCI order within each group.
    for move in sorted(board.legal_moves, key=lambda m: (not board.is_capture(m), m.uci())):
        board.push(move)
        score = -negamax(board, depth - 1, -beta, -alpha, ply + 1)
        board.pop()
        if score > best:
            best = score
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break
    return best


def rank_moves(board: chess.Board, depth: int = 2):
    """Score every legal root move; deterministic order (score desc, uci asc)."""
    rows = []
    for move in sorted(board.legal_moves, key=lambda m: m.uci()):
        board.push(move)
        score = -negamax(board, depth - 1, -MATE - 1, MATE + 1, 1)
        board.pop()
        rows.append({'move': move.uci(), 'cp': None if abs(score) >= MATE - 1000 else score,
                     'mate': None if abs(score) < MATE - 1000 else (MATE - abs(score) + 1) // 2 * (1 if score > 0 else -1),
                     'raw': score})
    rows.sort(key=lambda r: (-r['raw'], r['move']))
    for i, r in enumerate(rows, 1):
        r['rank'] = i
        r['pv'] = [r['move']]
    return rows


def candidates(board: chess.Board, depth: int = 2, top: int = 3):
    rows = rank_moves(board, depth)
    return rows[:top], {'depth': depth, 'nodes': None, 'searched_root_moves': len(rows)}
