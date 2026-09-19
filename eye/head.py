"""Train the retina head: feature print (768) -> label, a few thousand parameters.

    uv run python eye/head.py                 # train on eye/data, report, save eye/head.npz
    uv run python eye/head.py --holdout Slack # train on the other apps, test on Slack

The recipe is system-one-open's: cross-entropy plus Brier so the probabilities
are honest, class weights so the rare labels are learnt, then temperature
scaling on held-out cells. The head is a single linear layer (768 x 6 + 6);
training takes seconds, so collect more and run again whenever it is wrong.

Evaluation holds out whole captures (or one whole app) - cells from the same
screenshot are near-duplicates and would make a random split lie.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
WEIGHTS = HERE / "head.npz"

LABELS = ("blank", "text", "input", "icon", "image")
STEPS = 1500
LR = 0.05
BRIER = 1.0
L2 = 1e-4


FEATURES = ("fp", "px", "both")


def load(data: Path, features: str = "both", grid: int | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """x, y (label index), capture id, app name for every stored cell, deduplicated.
    `features`: fp = Vision feature print, px = pixel features, both = concatenated."""
    xs, ys, caps, apps = [], [], [], []
    for i, path in enumerate(sorted(data.glob("*/*.npz"))):
        body = np.load(path)
        parts = {"fp": body["x"], "px": body["px"]}
        x = np.concatenate([parts[k] for k in (("fp", "px") if features == "both" else (features,))], axis=1)
        keep = np.ones(len(x), dtype=bool) if grid is None else (body["meta"][:, 0] == grid)
        xs.append(x[keep])
        ys.append(np.array([LABELS.index(l) for l in body["y"][keep]]))
        caps.append(np.full(int(keep.sum()), i))
        apps.append(np.full(int(keep.sum()), str(body["app"])))
    if not xs:
        raise SystemExit(f"head: no data under {data}; run collect.py first")
    x, y, cap, app = np.concatenate(xs), np.concatenate(ys), np.concatenate(caps), np.concatenate(apps)
    # identical feature prints (the same cell captured twice) count once
    _, keep = np.unique(np.round(x, 4), axis=0, return_index=True)
    keep = np.sort(keep)
    return x[keep], y[keep], cap[keep], app[keep]


def softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def train(x: np.ndarray, y: np.ndarray, steps: int = STEPS, l2: float = L2) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Linear head with Adam on CE + Brier, class-weighted. Returns W, b, mean, std."""
    mean, std = x.mean(axis=0), x.std(axis=0) + 1e-6
    xn = (x - mean) / std
    n, d = xn.shape
    k = len(LABELS)
    counts = np.bincount(y, minlength=k).astype(np.float64)
    weights = np.where(counts > 0, n / (k * np.maximum(counts, 1)), 0.0)
    onehot = np.eye(k)[y]
    w = np.zeros((d, k))
    b = np.zeros(k)
    mw, vw, mb, vb = np.zeros_like(w), np.zeros_like(w), np.zeros_like(b), np.zeros_like(b)
    b1, b2, eps = 0.9, 0.999, 1e-8
    for t in range(1, steps + 1):
        p = softmax(xn @ w + b)
        sample_w = weights[y][:, None]
        # d/dz of CE is (p - onehot); of Brier sum((p - onehot)^2) it is 2 (p - onehot) * p (1 - p) roughly
        # via the softmax Jacobian; the exact form:
        diff = p - onehot
        g_brier = 2 * (p * (diff - (diff * p).sum(axis=1, keepdims=True)))
        gz = (diff + BRIER * g_brier) * sample_w / n
        gw = xn.T @ gz + l2 * w
        gb = gz.sum(axis=0)
        mw, vw = b1 * mw + (1 - b1) * gw, b2 * vw + (1 - b2) * gw * gw
        mb, vb = b1 * mb + (1 - b1) * gb, b2 * vb + (1 - b2) * gb * gb
        w -= LR * (mw / (1 - b1 ** t)) / (np.sqrt(vw / (1 - b2 ** t)) + eps)
        b -= LR * (mb / (1 - b1 ** t)) / (np.sqrt(vb / (1 - b2 ** t)) + eps)
    return w, b, mean, std


def predict(x: np.ndarray, w, b, mean, std, temperature: float = 1.0) -> np.ndarray:
    return softmax(((x - mean) / std @ w + b) / temperature)


def fit_temperature(logits_x: np.ndarray, y: np.ndarray, w, b, mean, std) -> float:
    """Temperature that minimises held-out NLL, by grid search."""
    z = (logits_x - mean) / std @ w + b
    best, best_t = np.inf, 1.0
    for t in np.linspace(0.5, 4.0, 71):
        p = softmax(z / t)
        nll = -np.log(p[np.arange(len(y)), y] + 1e-9).mean()
        if nll < best:
            best, best_t = nll, float(t)
    return best_t


def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    conf, pred = p.max(axis=1), p.argmax(axis=1)
    total = 0.0
    for i in range(bins):
        mask = (conf > i / bins) & (conf <= (i + 1) / bins)
        if mask.any():
            total += mask.mean() * abs((pred[mask] == y[mask]).mean() - conf[mask].mean())
    return float(total)


def report(name: str, p: np.ndarray, y: np.ndarray) -> None:
    pred = p.argmax(axis=1)
    print(f"{name}: {len(y)} cells, acc {np.mean(pred == y):.3f}, ECE {ece(p, y):.3f}")
    print(f"  {'label':7} {'n':>5} {'recall':>7} {'prec':>6}   picked as")
    for i, label in enumerate(LABELS):
        n = int((y == i).sum())
        if n == 0:
            continue
        recall = float((pred[y == i] == i).mean())
        prec = float((y[pred == i] == i).mean()) if (pred == i).any() else 0.0
        confusion = np.bincount(pred[y == i], minlength=len(LABELS))
        picked = " ".join(f"{LABELS[j]}:{c}" for j, c in enumerate(confusion) if c and j != i)
        print(f"  {label:7} {n:5} {recall:7.2f} {prec:6.2f}   {picked}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--holdout", help="an app name to hold out entirely; default: every 4th capture")
    parser.add_argument("--out", type=Path, default=WEIGHTS)
    parser.add_argument("--drop", action="append", default=[], help="drop cells with this label")
    parser.add_argument("--l2", type=float, default=L2)
    parser.add_argument("--features", choices=FEATURES, default="both")
    parser.add_argument("--grid", type=int, help="only cells from this grid width (16 or 48)")
    args = parser.parse_args()

    x, y, cap, app = load(args.data, args.features, args.grid)
    for label in args.drop:
        keep = y != LABELS.index(label)
        x, y, cap, app = x[keep], y[keep], cap[keep], app[keep]
    apps = sorted(set(app))
    print(f"data: {len(y)} cells, {len(set(cap))} captures, apps {apps}")
    print("  " + " ".join(f"{l}:{int((y == i).sum())}" for i, l in enumerate(LABELS)))

    test = (app == args.holdout) if args.holdout else (cap % 4 == 3)
    if not test.any() or test.all():
        raise SystemExit("head: the split leaves one side empty")
    w, b, mean, std = train(x[~test], y[~test], l2=args.l2)
    t = fit_temperature(x[test], y[test], w, b, mean, std)
    report("train", predict(x[~test], w, b, mean, std, t), y[~test])
    report(f"held out ({args.holdout or 'every 4th capture'}), T={t:.2f}", predict(x[test], w, b, mean, std, t), y[test])

    # the shipped head is trained on everything, with the held-out temperature
    w, b, mean, std = train(x, y, l2=args.l2)
    np.savez(args.out, w=w, b=b, mean=mean, std=std, temperature=t, labels=np.array(LABELS), features=args.features)
    print(f"saved {args.out} ({w.size + b.size} parameters)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
