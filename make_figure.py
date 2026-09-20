"""Build figure/answers_by_order.png from the raw files in results/.

Every cell is the tier a system chose for one message under one option order.
A row that changes colour is a message whose answer depends on option order.
"""

import json
import pathlib

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

HERE = pathlib.Path(__file__).parent
RES = HERE / "results"
CASES = ["clear_high_risk_scam", "benign_smalltalk", "ambiguous_urgent",
         "technical_neutral", "mild_concern", "empty_string"]
ORDER_KEYS = ["orig_low_med_high", "reversed_high_med_low", "rotated_med_high_low"]
ORDER_LABELS = ["low, med, high", "high, med, low", "med, high, low"]
TIERS = ["low", "medium", "high"]


def read_clone(name: str) -> dict[str, list[str]]:
    rows = {}
    for line in (RES / name).read_text().splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] in CASES:
            rows[parts[0]] = [p.split("(")[0] for p in parts[1:]]
    return rows


def read_jev() -> dict[str, list[str]]:
    data = json.loads(next(RES.glob("exp6_results_*.json")).read_text())["passes"]
    rows = {}
    for c in CASES:
        picks = [data["pass_1"][c][o]["risk_tier_choice"] for o in ORDER_KEYS]
        assert picks == [data["pass_2"][c][o]["risk_tier_choice"] for o in ORDER_KEYS]
        rows[c] = picks
    return rows


PANELS = [
    ("jevmlx, scoring=slots (default)", read_clone("clone-run-1.txt")),
    ("jevmlx, slots + prior_correction", read_clone("clone-prior-correction.txt")),
    ("jevmlx, scoring=labels", read_clone("clone-labels.txt")),
    ("jevmlx, labels + prior_correction", read_clone("clone-labels-prior.txt")),
    ("Jev (hosted, jev-1.13.0), both passes", read_jev()),
]

cmap = ListedColormap(["C0", "C1", "C3"])
fig, axes = plt.subplots(2, 3, figsize=(15, 9.5), constrained_layout=True)
for ax, (title, rows) in zip(axes.flat, PANELS):
    grid = np.array([[TIERS.index(v) for v in rows[c]] for c in CASES])
    ax.imshow(grid, cmap=cmap, vmin=0, vmax=2, aspect="auto")
    for i, c in enumerate(CASES):
        for j, v in enumerate(rows[c]):
            ax.text(j, i, v, ha="center", va="center", color="white", fontsize=11)
    flips = sum(len(set(rows[c])) > 1 for c in CASES)
    ax.set_title(f"{title}\n{flips}/6 messages change with order", fontsize=11)
    ax.set_xticks(range(3), ORDER_LABELS, fontsize=9)
    ax.set_yticks(range(6), CASES, fontsize=9)
    ax.set_xlabel("option order in the prompt / criteria map", fontsize=9)
axes.flat[-1].axis("off")
axes.flat[-1].text(
    0.0, 0.5,
    "Same 6 messages, same option text.\n"
    "Only the option order changes.\n\n"
    "A row that changes colour:\n"
    "the answer depends on order.\n\n"
    "Qwen2.5-1.5B-Instruct-4bit\njevmlx @ bcdb12c\n"
    "n = 6, no ground truth.\n"
    "github.com/imaddde867/jev-position-test",
    fontsize=10.5, va="center", family="monospace",
)
out = HERE / "figure" / "answers_by_order.png"
fig.savefig(out, dpi=110)
print(out)
