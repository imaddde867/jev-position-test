"""
Position-sensitivity test for jevmlx, an open-source clone of the Jev
interface (constrained answer scoring on a local MLX model).

Six short messages, one 3-option enum (risk_tier: low / medium / high), three
orderings of the same options with the same per-option descriptions. If the
chosen tier changes when only the order changes, position is leaking into
the answer.

Needs Apple Silicon. Install the pinned clone first:
    pip install "jevmlx @ git+https://github.com/bnsd55/openjev@bcdb12cb3e3726f1691849bfdb6fb099c15c1933"

--scoring defaults to "slots" here on purpose: that was jevmlx's default at
bcdb12c. jevmlx later switched its library default to "labels" (PR #103).
"""

import json
from importlib.metadata import PackageNotFoundError, distribution
from typing import Literal

import mlx.core as mx
from pydantic import BaseModel, Field

import jevmlx  # noqa: E402

MODEL = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"

CASES = {
    "clear_high_risk_scam": (
        "URGENT: Your account will be suspended in 1 hour. Click this link "
        "and enter your card number and PIN immediately to avoid permanent "
        "loss of funds: bit.ly/verify-now-2847"
    ),
    "benign_smalltalk": (
        "Hey, just checking in -- how was your weekend? We should grab "
        "coffee sometime next week if you're free."
    ),
    "ambiguous_urgent": (
        "I need you to process this wire transfer today, the client is "
        "waiting and I can't get on a call right now, just use the account "
        "details from last time."
    ),
    "technical_neutral": (
        "Sensor 14B reported a temperature reading of 22.4C at 03:00 UTC, "
        "within the configured normal operating range."
    ),
    "mild_concern": (
        "I noticed a $40 charge I don't remember making, probably a "
        "subscription I forgot about, can you check it when you get a "
        "chance?"
    ),
    "empty_string": "",
}


# Same option descriptions as jev_hosted_position.py, so both systems see the
# same rubric. An earlier run gave jevmlx bare option words only; adding the
# descriptions did not remove the position effect (one more case flipped).
TIER_DESCRIPTIONS = {
    "low": "Low risk: no red flags, safe to proceed as normal.",
    "medium": "Some risk indicators present, needs human review before acting.",
    "high": "Clear risk indicators: likely fraudulent, malicious, or urgent harm.",
}


def make_model(order: tuple[str, str, str]) -> type[BaseModel]:
    lit = Literal[order]  # type: ignore[valid-type]

    class RiskGate(BaseModel):
        is_risky: bool = Field(
            description="Does this message show signs of risk, scam, fraud, or urgent harm?"
        )
        risk_tier: lit = Field(  # type: ignore[valid-type]
            description="What risk tier does this message fall into?",
            json_schema_extra={"choice_descriptions": TIER_DESCRIPTIONS},
        )

    RiskGate.__name__ = f"RiskGate_{'_'.join(order)}"
    return RiskGate


ORDERS = {
    "orig_low_med_high": ("low", "medium", "high"),
    "reversed_high_med_low": ("high", "medium", "low"),
    "rotated_med_high_low": ("medium", "high", "low"),
}


def measurement_1_permutation(scoring: str = "slots", prior_correction: bool = False,
                              compact: bool = False):
    if compact:
        return _compact_table(scoring, prior_correction)
    print("=" * 100)
    print("MEASUREMENT 1: does risk_tier track enum POSITION in the prompt?")
    print(f"settings: scoring={scoring} prior_correction={prior_correction}")
    print("=" * 100)
    header = f"{'case':<24}" + "".join(f"{name:<26}" for name in ORDERS)
    print(header)
    for case_name, ctx in CASES.items():
        row = f"{case_name:<24}"
        for order_name, order in ORDERS.items():
            model_cls = make_model(order)
            d = jevmlx.decide(
                model_cls, ctx, model=MODEL,
                scoring=scoring, prior_correction=prior_correction,
            )
            fr = d.fields["risk_tier"]
            cell = f"{fr.value}(m={fr.log_score_margin:.3f})"
            row += f"{cell:<26}"
        print(row)
    print()
    print("Reading this: if the CHOSEN value changes with the option's slot")
    print("position (not its meaning) across columns, that's position bias,")
    print("not a semantic 'medium' prior. If it stays semantically the same")
    print("regardless of where it sits, position is cleared.")
    print()


def _compact_table(scoring: str, prior_correction: bool):
    """Same decisions as the full table, narrower layout (2-decimal margins)."""
    print(f"scoring={scoring}  prior_correction={prior_correction}")
    print("option order ->        " + "".join(f"{','.join(o).replace('medium', 'med'):<16}" for o in ORDERS.values()))
    for case_name, ctx in CASES.items():
        row = f"{case_name:<23}"
        for order in ORDERS.values():
            d = jevmlx.decide(
                make_model(order), ctx, model=MODEL,
                scoring=scoring, prior_correction=prior_correction,
            )
            fr = d.fields["risk_tier"]
            row += f"{fr.value + f'(m={fr.log_score_margin:.2f})':<16}"
        print(row)


if __name__ == "__main__":
    commit = "unknown"
    try:
        raw = distribution("jevmlx").read_text("direct_url.json")
        if raw:
            info = json.loads(raw)
            commit = info.get("vcs_info", {}).get("commit_id") or info.get("url", commit)
    except PackageNotFoundError:
        pass
    import mlx_lm  # noqa: E402
    import argparse  # noqa: E402

    ap = argparse.ArgumentParser()
    ap.add_argument("--scoring", choices=["slots", "labels"], default="slots",
                    help="jevmlx scoring mode (default slots: the library default at bcdb12c)")
    ap.add_argument("--prior-correction", action="store_true",
                    help="subtract jevmlx's neutral-context prior before choosing")
    ap.add_argument("--compact", action="store_true",
                    help="narrower output (same decisions, 2-decimal margins)")
    args = ap.parse_args()
    if args.compact:
        print(f"jevmlx {commit[:7]}  {MODEL.split('/')[-1]}  mlx {mx.__version__}")
    else:
        print(f"jevmlx source: {commit}")
        print(f"model: {MODEL}  mlx: {mx.__version__}  mlx_lm: {mlx_lm.__version__}")
    measurement_1_permutation(args.scoring, args.prior_correction, args.compact)
