"""Follow a list of terms you choose, by leaning group, quarter by quarter.

Put the terms in watch_terms.txt (one per line, a single word or a two-word phrase;
lines starting with # are ignored). Terms are matched the way build_terms.py counts them:
lower case, without stopwords, so "defund the police" cannot be tracked but "defund" can.

Writes (next to this script):
  watch_trends.csv    rate per 1,000 headlines, per term, quarter and group
  watch_by_outlet.csv rate per 1,000 headlines per term and outlet, whole period
  watch_trends.png    one small chart per term, one line per group

Usage: python track_terms.py
"""
import collections
import csv
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from build_terms import STOPWORDS, terms_of
from db import HERE, connect
from lean_terms import GROUP_MAP, MIN_OUTLET_QUARTER_HEADLINES, load_outlets

COLORS = {"left": "#2a6fb0", "center": "#7a7a7a", "right": "#c0392b"}


def load_watch():
    path = HERE / "watch_terms.txt"
    if not path.exists():
        sys.exit("Create watch_terms.txt in the project folder first (one term per line).")
    terms = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        t = ln.strip().lower()
        if not t or t.startswith("#"):
            continue
        if t not in terms_of(t):          # same normalisation the counter used
            print(f"Cannot track '{t}' (stopwords or more than two words). Try: "
                  f"{sorted(terms_of(t))[:4]}")
            continue
        terms.append(t)
    return terms


def main():
    watch = load_watch()
    if not watch:
        sys.exit("No usable terms in watch_terms.txt")
    info, _ = load_outlets()
    conn = connect()
    totals = {(q, o): n for q, o, n in conn.execute(
        "SELECT quarter, outlet_id, headlines FROM quarter_totals")
        if o in info and n >= MIN_OUTLET_QUARTER_HEADLINES}
    quarters = sorted({q for q, _ in totals})

    marks = ",".join("?" * len(watch))
    counts = {(t, q, o): n for t, q, o, n in conn.execute(
        f"SELECT term, quarter, outlet_id, n FROM term_counts WHERE term IN ({marks})", watch)}

    rows, by_outlet = [], []
    series = {}
    for t in watch:
        for q in quarters:
            for g in ("left", "center", "right"):
                outs = [o for (qq, o) in totals if qq == q and info[o][0] == g]
                if not outs:
                    continue
                rate = sum(1000.0 * counts.get((t, q, o), 0) / totals[(q, o)] for o in outs) / len(outs)
                rows.append((t, q, g, round(rate, 3), len(outs)))
                series[(t, g, q)] = rate
        per = collections.defaultdict(lambda: [0, 0])
        for (q, o), h in totals.items():
            per[o][0] += counts.get((t, q, o), 0)
            per[o][1] += h
        for o, (n, h) in sorted(per.items()):
            by_outlet.append((t, o, info[o][0], n, h, round(1000.0 * n / h, 3)))

    for name, header, data in (
            ("watch_trends.csv", ["term", "quarter", "group", "per_1000", "outlets"], rows),
            ("watch_by_outlet.csv", ["term", "outlet", "group", "headlines_with_term",
                                     "outlet_headlines", "per_1000"], by_outlet)):
        with open(HERE / name, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(data)
        print("wrote", HERE / name)

    ncols = 3
    nrows = (len(watch) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 2.8 * nrows), squeeze=False,
                             sharex=True)
    xs = list(range(len(quarters)))
    ticks = [i for i, q in enumerate(quarters) if q.endswith("Q1")]
    for ax, t in zip(axes.flat, watch):
        for g in ("left", "center", "right"):
            ys = [series.get((t, g, q), float("nan")) for q in quarters]
            ax.plot(xs, ys, color=COLORS[g], label=g, linewidth=1.8)
        ax.set_title(t, fontsize=11, loc="left")
        ax.set_xticks(ticks)
        ax.set_xticklabels([quarters[i][:4] for i in ticks], fontsize=8)
        ax.set_ylabel("per 1,000 headlines", fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    for ax in list(axes.flat)[len(watch):]:
        ax.axis("off")
    axes.flat[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(HERE / "watch_trends.png", dpi=150)
    print("wrote", HERE / "watch_trends.png")


if __name__ == "__main__":
    main()