"""Jev에게 체스를 두게 한다: 합법수 전부를 후보로 주고 하나를 고르게 한다.

가설: Jev는 "주어진 후보 중 조건에 맞는 것"은 잘 고르지만 "존재하지 않는 다음 것"은
만들지 못한다. 그래서 후보 설명을 두 가지로 준다.

  bare       설명 없이 SAN 라벨만 (criteria 값이 전부 None)
  annotated  코드가 계산한 사실 한 줄 (잡기, 체크, 도착 칸 안전도, 매달린 말, 중앙 통제 …)

상대는 random / greedy / sf1(Stockfish depth 1). Jev의 매 수는 Stockfish depth 12로
채점해 centipawn 손실을 남긴다.

실행:
    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Personal/typesafe jev key/credential"') \
      -- uv run python experiments/chess/play.py --games 10 --workers 4
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine
import chess.pgn

sys.path.insert(0, str(Path(__file__).parent))
from live_server import EventBus, LiveServer  # noqa: E402

from typesafe_sdk import Choice, TypeSafeClient  # noqa: E402

HERE = Path(__file__).parent
LIVE_HTML = HERE / "live.html"

SEED = 42
EVAL_DEPTH = 12
SF1_DEPTH = 1
MATE_SCORE = 1000
CP_LOSS_CAP = 1000
BLUNDER_CP = 300
HISTORY_MOVES = 6
CENTER = [chess.D4, chess.D5, chess.E4, chess.E5]

VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
PIECE_KO = {
    chess.PAWN: "폰",
    chess.KNIGHT: "나이트",
    chess.BISHOP: "비숍",
    chess.ROOK: "룩",
    chess.QUEEN: "퀸",
    chess.KING: "킹",
}

INSTRUCTIONS = (
    "현재 국면에서 가장 좋은 다음 수를 고른다. "
    "체크메이트 > 안전한 재료 이득 > 위협 회피 > 중앙·전개 순으로 판단한다."
)


# --------------------------------------------------------------------------- 국면 서술


def ascii_board(board: chess.Board) -> str:
    """str(board)에 랭크 번호와 파일 문자를 붙인다."""
    rows = str(board).split("\n")
    lines = [f"{8 - i} {row}" for i, row in enumerate(rows)]
    lines.append("  a b c d e f g h")
    return "\n".join(lines)


def material(board: chess.Board) -> int:
    score = 0
    for piece_type, value in VALUE.items():
        if piece_type is chess.KING:
            continue
        score += value * len(board.pieces(piece_type, chess.WHITE))
        score -= value * len(board.pieces(piece_type, chess.BLACK))
    return score


def castling_text(board: chess.Board) -> str:
    rights = board.fen().split(" ")[2]
    return "없음" if rights == "-" else rights


def make_state(board: chess.Board, history: list[str]) -> str:
    turn = "백" if board.turn == chess.WHITE else "흑"
    recent = history[-HISTORY_MOVES:]
    mat = material(board)
    return (
        f"둘 차례: {turn}\n"
        f"FEN: {board.fen()}\n"
        f"보드:\n{ascii_board(board)}\n"
        f"재료 점수(백-흑): {mat:+d}\n"
        f"체크: {'예' if board.is_check() else '아니오'}\n"
        f"캐슬링 권리: {castling_text(board)}\n"
        f"이전 수: {' '.join(recent) if recent else '없음'}"
    )


def center_control(board: chess.Board, color: chess.Color) -> int:
    return sum(1 for sq in CENTER if board.attackers(color, sq))


def king_zone_pressure(board: chess.Board, color: chess.Color) -> int:
    """상대 킹 주변 8칸 중 color가 공격하는 칸 수."""
    ksq = board.king(not color)
    if ksq is None:
        return 0
    ring = chess.SquareSet(chess.BB_KING_ATTACKS[ksq])
    return sum(1 for sq in ring if board.attackers(color, sq))


def hanging_count(board: chess.Board, color: chess.Color) -> int:
    """공격받고 있으면서 아무도 지키지 않는 color의 말 수(킹 제외)."""
    hang = 0
    for sq, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type == chess.KING:
            continue
        if board.attackers(not color, sq) and not board.attackers(color, sq):
            hang += 1
    return hang


def annotate(board: chess.Board, move: chess.Move) -> str:
    """코드가 계산한 사실만으로 수 하나를 한 줄로 설명한다."""
    mover = board.turn
    piece = board.piece_at(move.from_square)
    parts: list[str] = []

    if board.is_castling(move):
        side = "킹사이드" if chess.square_file(move.to_square) > chess.square_file(move.from_square) else "퀸사이드"
        parts.append(f"{side} 캐슬링.")
    else:
        name = PIECE_KO[piece.piece_type] if piece else "말"
        parts.append(f"{name} {chess.square_name(move.from_square)}→{chess.square_name(move.to_square)}.")

    if board.is_capture(move):
        captured = chess.PAWN if board.is_en_passant(move) else board.piece_at(move.to_square).piece_type
        parts.append(f"{PIECE_KO[captured]} 잡기(가치 {VALUE[captured]}).")
    else:
        parts.append("잡기 없음.")

    if move.promotion:
        parts.append(f"{PIECE_KO[move.promotion]}로 승격.")

    center_before = center_control(board, mover)
    pressure_before = king_zone_pressure(board, mover)

    board.push(move)
    try:
        if board.is_checkmate():
            parts.append("체크메이트.")
        elif board.is_check():
            parts.append("체크.")
        attackers = len(board.attackers(not mover, move.to_square))
        defenders = len(board.attackers(mover, move.to_square))
        if attackers == 0:
            safety = "안전"
        elif defenders >= attackers:
            safety = "방어됨"
        else:
            safety = "위험"
        parts.append(f"도착 칸 {safety}(공격 {attackers}, 방어 {defenders}).")
        parts.append(f"이 수 뒤 매달린 아군 말 {hanging_count(board, mover)}개.")
        center_after = center_control(board, mover)
        parts.append(f"중앙 통제 {center_after - center_before:+d}(총 {center_after}).")
        pressure_after = king_zone_pressure(board, mover)
        parts.append(f"상대 킹 주변 공격 {pressure_after}칸({pressure_after - pressure_before:+d}).")
    finally:
        board.pop()

    return " ".join(parts)


def criteria_for(board: chess.Board, style: str) -> tuple[dict[str, str | None], dict[str, chess.Move]]:
    """합법수 전부를 SAN 라벨로 만든다. bare는 설명 없음, annotated는 계산된 사실 한 줄."""
    crit: dict[str, str | None] = {}
    by_san: dict[str, chess.Move] = {}
    for move in board.legal_moves:
        san = board.san(move)
        by_san[san] = move
        crit[san] = None if style == "bare" else annotate(board, move)
    return crit, by_san


# --------------------------------------------------------------------------- 상대


def opponent_move(kind: str, board: chess.Board, rng: random.Random, engine) -> chess.Move:
    moves = list(board.legal_moves)
    if kind == "random":
        return rng.choice(moves)
    if kind == "greedy":
        for move in moves:
            board.push(move)
            mate = board.is_checkmate()
            board.pop()
            if mate:
                return move
        best_value, best_moves = 0, []
        for move in moves:
            if not board.is_capture(move):
                continue
            captured = chess.PAWN if board.is_en_passant(move) else board.piece_at(move.to_square).piece_type
            value = VALUE[captured]
            if value > best_value:
                best_value, best_moves = value, [move]
            elif value == best_value and best_moves:
                best_moves.append(move)
        if best_moves:
            return rng.choice(best_moves)
        return rng.choice(moves)
    if kind == "sf1":
        result = engine.play(board, chess.engine.Limit(depth=SF1_DEPTH))
        return result.move if result.move is not None else rng.choice(moves)
    raise ValueError(f"unknown opponent: {kind}")


# --------------------------------------------------------------------------- 수 평가


def pov_cp(score: chess.engine.PovScore, color: chess.Color) -> int:
    cp = score.pov(color).score(mate_score=MATE_SCORE)
    return max(-MATE_SCORE, min(MATE_SCORE, cp))


def evaluate(engine, board: chess.Board, move: chess.Move) -> tuple[int | None, str | None, str | None]:
    """둔 쪽 관점의 (cp_loss, best_san, best_uci). 엔진이 실패하면 전부 None."""
    color = board.turn
    limit = chess.engine.Limit(depth=EVAL_DEPTH)
    try:
        best_info = engine.analyse(board, limit)
        pv = best_info.get("pv") or []
        best_move = pv[0] if pv else None
        best_cp = pov_cp(best_info["score"], color)
        played_info = engine.analyse(board, limit, root_moves=[move])
        played_cp = pov_cp(played_info["score"], color)
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, KeyError, IndexError):
        return None, None, None
    loss = max(0, min(CP_LOSS_CAP, best_cp - played_cp))
    if best_move is None:
        return loss, None, None
    return loss, board.san(best_move), best_move.uci()


# --------------------------------------------------------------------------- 스레드별 자원


class Resources(threading.local):
    client: TypeSafeClient | None = None
    engine = None
    sf1 = None


RESOURCES = Resources()
_OPEN: list = []
_OPEN_LOCK = threading.Lock()
STOCKFISH = shutil.which("stockfish")


def _new_engine():
    if STOCKFISH is None:
        raise RuntimeError("stockfish를 PATH에서 찾지 못했다")
    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
    with _OPEN_LOCK:
        _OPEN.append(engine)
    return engine


def get_client() -> TypeSafeClient:
    if RESOURCES.client is None:
        RESOURCES.client = TypeSafeClient()
    return RESOURCES.client


def get_engine():
    if RESOURCES.engine is None:
        RESOURCES.engine = _new_engine()
    return RESOURCES.engine


def get_sf1():
    if RESOURCES.sf1 is None:
        RESOURCES.sf1 = _new_engine()
    return RESOURCES.sf1


def close_engines() -> None:
    with _OPEN_LOCK:
        engines, _OPEN[:] = list(_OPEN), []
    for engine in engines:
        try:
            engine.quit()
        except Exception:  # noqa: BLE001 — 종료 경로, 실패해도 무시
            pass


# --------------------------------------------------------------------------- 한 판


def play_game(spec: dict, bus: EventBus | None, max_plies: int) -> dict:
    style, opponent, jev_color = spec["style"], spec["opponent"], spec["jev_color"]
    rng = random.Random(spec["seed"])
    client = get_client()
    engine = get_engine()
    sf1 = get_sf1() if opponent == "sf1" else None

    board = chess.Board()
    game_record = {
        "id": spec["id"],
        "style": style,
        "opponent": opponent,
        "jev_color": "white" if jev_color == chess.WHITE else "black",
        "seed": spec["seed"],
        "result": "*",
        "outcome": "unfinished",
        "plies": 0,
        "pgn": "",
        "moves": [],
    }
    if bus is not None:
        bus.publish("game_start", {
            "game_id": spec["id"],
            "slot": spec.get("slot"),
            "style": style,
            "opponent": opponent,
            "jev_color": game_record["jev_color"],
            "cell": f"{style}/{opponent}",
        })

    history: list[str] = []
    model = None
    try:
        while not board.is_game_over(claim_draw=True) and board.ply() < max_plies:
            fen_before = board.fen()
            by_jev = board.turn == jev_color
            if by_jev:
                crit, by_san = criteria_for(board, style)
                state = make_state(board, history)
                t0 = time.perf_counter()
                resp = client.system_one(
                    state=state,
                    questions={"move": Choice(instructions=INSTRUCTIONS, criteria=crit)},
                )
                latency = (time.perf_counter() - t0) * 1000
                model = resp.model
                answer = resp.answers["move"]
                probs = sorted(answer.probabilities.items(), key=lambda kv: -kv[1])
                san = next(
                    (label for label in [answer.choice, *(p[0] for p in probs)] if label in by_san),
                    next(iter(by_san)),
                )
                move = by_san[san]
                cp_loss, best_san, best_uci = evaluate(engine, board, move)
                entry = {
                    "ply": board.ply(),
                    "san": san,
                    "by": "jev",
                    "fen_before": fen_before,
                    "latency_ms": round(latency, 1),
                    "confidence": answer.confidence,
                    "top5": [[label, prob] for label, prob in probs[:5]],
                    "cp_loss": cp_loss,
                    "best_san": best_san,
                    "input_tokens": resp.usage.input_tokens,
                }
                top5_live = [[label, by_san[label].uci() if label in by_san else None, prob]
                             for label, prob in probs[:5]]
            else:
                move = opponent_move(opponent, board, rng, sf1)
                san = board.san(move)
                entry = {
                    "ply": board.ply(),
                    "san": san,
                    "by": "opp",
                    "fen_before": fen_before,
                    "latency_ms": None,
                    "confidence": None,
                    "top5": None,
                    "cp_loss": None,
                    "best_san": None,
                    "input_tokens": None,
                }
                top5_live, best_uci = None, None

            uci = move.uci()
            board.push(move)
            history.append(san)
            game_record["moves"].append(entry)
            game_record["plies"] = board.ply()
            if bus is not None:
                bus.publish("move", {
                    "game_id": spec["id"],
                    "ply": entry["ply"],
                    "san": san,
                    "uci": uci,
                    "by": entry["by"],
                    "fen": board.fen(),
                    "confidence": entry["confidence"],
                    "top5": top5_live,
                    "cp_loss": entry["cp_loss"],
                    "best_uci": best_uci,
                })

        if board.is_game_over(claim_draw=True):
            game_record["result"] = board.result(claim_draw=True)
        else:
            game_record["result"] = "*"
        game_record["outcome"] = outcome_of(game_record["result"], jev_color)
    except Exception as exc:  # noqa: BLE001 — 한 판의 실패가 전체를 멈추지 않게
        game_record["outcome"] = "error"
        game_record["error"] = f"{type(exc).__name__}: {exc}"

    game_record["pgn"] = to_pgn(board, game_record)
    game_record["model"] = model
    game_record["mean_cp_loss"] = mean_cp_loss(game_record)
    if bus is not None:
        bus.publish("game_end", {
            "game_id": spec["id"],
            "result": game_record["result"],
            "outcome": game_record["outcome"],
            "plies": game_record["plies"],
            "mean_cp_loss": game_record["mean_cp_loss"],
        })
    return game_record


def outcome_of(result: str, jev_color: chess.Color) -> str:
    if result == "1/2-1/2":
        return "draw"
    if result == "1-0":
        return "win" if jev_color == chess.WHITE else "loss"
    if result == "0-1":
        return "loss" if jev_color == chess.WHITE else "win"
    return "unfinished"


def to_pgn(board: chess.Board, record: dict) -> str:
    game = chess.pgn.Game.from_board(board)
    game.headers["Event"] = "jev-chess"
    game.headers["White"] = "Jev" if record["jev_color"] == "white" else record["opponent"]
    game.headers["Black"] = record["opponent"] if record["jev_color"] == "white" else "Jev"
    game.headers["Result"] = record["result"]
    game.headers["Round"] = str(record["id"])
    return game.accept(chess.pgn.StringExporter(headers=False, variations=False, comments=False)).strip()


def jev_losses(record: dict) -> list[int]:
    return [m["cp_loss"] for m in record["moves"] if m["by"] == "jev" and isinstance(m["cp_loss"], int)]


def mean_cp_loss(record: dict) -> float | None:
    losses = jev_losses(record)
    return round(statistics.fmean(losses), 1) if losses else None


# --------------------------------------------------------------------------- 요약


def summarize(games: list[dict]) -> dict:
    cells: dict[str, dict] = {}
    for record in games:
        key = f"{record['style']}/{record['opponent']}"
        cell = cells.setdefault(key, {
            "games": 0, "win": 0, "draw": 0, "loss": 0, "unfinished": 0, "error": 0,
            "_losses": [], "_confs": [],
        })
        cell["games"] += 1
        cell[record["outcome"]] = cell.get(record["outcome"], 0) + 1
        cell["_losses"].extend(jev_losses(record))
        cell["_confs"].extend(
            m["confidence"] for m in record["moves"]
            if m["by"] == "jev" and isinstance(m["confidence"], (int, float))
        )
    out = {}
    for key, cell in sorted(cells.items()):
        losses, confs = cell.pop("_losses"), cell.pop("_confs")
        out[key] = {
            **cell,
            "moves": len(losses),
            "mean_cp_loss": round(statistics.fmean(losses), 1) if losses else None,
            "median_cp_loss": round(statistics.median(losses), 1) if losses else None,
            "mean_conf": round(statistics.fmean(confs), 4) if confs else None,
            "blunders": round(sum(1 for x in losses if x >= BLUNDER_CP) / len(losses), 4) if losses else None,
        }
    return out


# --------------------------------------------------------------------------- 실행


def build_specs(args) -> list[dict]:
    specs = []
    for cell_index, (style, opponent) in enumerate(
        (s, o) for s in args.styles for o in args.opponents
    ):
        for i in range(args.games):
            specs.append({
                "id": len(specs) + 1,
                "style": style,
                "opponent": opponent,
                "jev_color": chess.WHITE if i % 2 == 0 else chess.BLACK,
                "seed": SEED * 1_000_003 + cell_index * 1_000 + i,
            })
    return specs


def main() -> int:
    parser = argparse.ArgumentParser(description="Jev가 두는 체스 대국")
    parser.add_argument("--games", type=int, default=10, help="셀당 판 수")
    parser.add_argument("--workers", type=int, default=4, help="동시 대국 수")
    parser.add_argument("--styles", default="bare,annotated")
    parser.add_argument("--opponents", default="random,greedy,sf1")
    parser.add_argument("--max-plies", type=int, default=200)
    parser.add_argument("--live", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--out", default="experiments/chess/results.json")
    args = parser.parse_args()
    args.styles = [s.strip() for s in args.styles.split(",") if s.strip()]
    args.opponents = [s.strip() for s in args.opponents.split(",") if s.strip()]

    if "sf1" in args.opponents and STOCKFISH is None:
        print("stockfish를 찾지 못했다 (PATH 확인)", file=sys.stderr)
        return 2
    if STOCKFISH is None:
        print("stockfish 없이는 수 평가를 할 수 없다", file=sys.stderr)
        return 2
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("TYPESAFE_API_KEY가 없다", file=sys.stderr)
        return 2

    random.seed(SEED)
    specs = build_specs(args)
    slots = max(1, min(args.workers, 4))
    for spec in specs:
        spec["slot"] = None

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    bus: EventBus | None = None
    server: LiveServer | None = None
    if args.live:
        bus = EventBus()
        try:
            server = LiveServer(bus, LIVE_HTML, args.port)
            print(f"라이브 보드: {server.start()}", flush=True)
        except OSError as exc:
            print(f"라이브 서버를 열지 못했다({exc}); 라이브 없이 계속한다", flush=True)
            bus, server = None, None

    config = {
        "games_per_cell": args.games,
        "workers": args.workers,
        "styles": args.styles,
        "opponents": args.opponents,
        "max_plies": args.max_plies,
        "seed": SEED,
        "eval_depth": EVAL_DEPTH,
        "sf1_depth": SF1_DEPTH,
        "blunder_cp": BLUNDER_CP,
        "stockfish": STOCKFISH,
    }

    games: list[dict] = []
    write_lock = threading.Lock()
    free_slots = list(range(slots))
    slot_lock = threading.Lock()
    total = len(specs)
    t_start = time.perf_counter()

    def run_one(spec: dict) -> dict:
        with slot_lock:
            spec["slot"] = free_slots.pop(0) if free_slots else None
        try:
            return play_game(spec, bus, args.max_plies)
        finally:
            with slot_lock:
                if spec["slot"] is not None:
                    free_slots.append(spec["slot"])

    def finish(record: dict) -> None:
        with write_lock:
            games.append(record)
            summary = summarize(games)
            payload = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "model": next((g.get("model") for g in games if g.get("model")), None),
                "config": config,
                "games": sorted(games, key=lambda g: g["id"]),
                "summary": summary,
            }
            tmp = out_path.with_suffix(out_path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(out_path)
            done = len(games)
            mean = record["mean_cp_loss"]
            print(
                f"[{done}/{total}] {record['style']} vs {record['opponent']}  "
                f"Jev={record['jev_color']}  {record['result']} ({record['outcome']})  "
                f"plies={record['plies']}  cp_loss mean {mean if mean is not None else '-'}",
                flush=True,
            )
            if record.get("error"):
                print(f"        error: {record['error']}", flush=True)
            if bus is not None:
                bus.publish("summary", {"cells": summary, "done": done, "total": total})

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(run_one, spec) for spec in specs]
            for future in as_completed(futures):
                finish(future.result())
    finally:
        close_engines()

    elapsed = time.perf_counter() - t_start
    calls = sum(1 for g in games for m in g["moves"] if m["by"] == "jev")
    print(f"\n저장: {out_path}  (판 {len(games)}, Jev 호출 {calls}회, {elapsed:.0f}초)", flush=True)
    for key, cell in summarize(games).items():
        print(
            f"  {key:22s} W{cell['win']} D{cell['draw']} L{cell['loss']} "
            f"U{cell['unfinished']} E{cell['error']}  "
            f"cp_loss mean {cell['mean_cp_loss']} median {cell['median_cp_loss']}  "
            f"conf {cell['mean_conf']}  blunder {cell['blunders']}",
            flush=True,
        )
    if server is not None:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
