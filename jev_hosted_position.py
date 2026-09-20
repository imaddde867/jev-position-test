"""
Same position-sensitivity test as clone_jevmlx_position.py, run against
TypeSafe's hosted Jev ("jev-latest") instead of the local clone. Same 6
cases, same option descriptions, same 3 risk_tier orderings.

Question: does real Jev's chosen risk_tier change when only the order of
the criteria map changes? Each ordering is sent twice (pass 1, pass 2) as a
control: if same-order repeats return identical confidences while different
orderings return different ones, the order reached the model (the API did
not canonicalize the map). JSON objects are unordered by spec and the docs
do not say whether key order is preserved.

Writes raw results to results/exp6_results_<UTC timestamp>.json.

Reads TYPESAFE_API_KEY from the environment. Never prints the key.
"""

import datetime
import json
import os
import pathlib
import sys
import time

import requests

API_KEY = os.environ.get("TYPESAFE_API_KEY")
if not API_KEY:
    sys.exit("TYPESAFE_API_KEY not set in environment.")

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"

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

TIER_DESCRIPTIONS = {
    "low": "Low risk: no red flags, safe to proceed as normal.",
    "medium": "Some risk indicators present, needs human review before acting.",
    "high": "Clear risk indicators: likely fraudulent, malicious, or urgent harm.",
}

ORDERS = {
    "orig_low_med_high": ["low", "medium", "high"],
    "reversed_high_med_low": ["high", "medium", "low"],
    "rotated_med_high_low": ["medium", "high", "low"],
}


def call_jev(state: str, order: list[str], retries: int = 4) -> dict:
    body = {
        "state": state,
        "model": MODEL,
        "questions": {
            "is_risky": {
                "type": "noul",
                "instructions": "Does this message show signs of risk, scam, fraud, or urgent harm?",
            },
            "risk_tier": {
                "type": "choice",
                "instructions": "What risk tier does this message fall into?",
                "criteria": {k: TIER_DESCRIPTIONS[k] for k in order},
            },
        },
    }
    delay = 1.0
    for attempt in range(retries):
        r = requests.post(
            ENDPOINT,
            json=body,
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=30,
        )
        if r.status_code in (429, 529):
            time.sleep(delay)
            delay *= 2
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return {}


def run_pass(pass_no: int) -> dict:
    print("=" * 100)
    print(f"REAL JEV, pass {pass_no}: does risk_tier track option ORDER in the criteria map?")
    print("=" * 100)
    header = f"{'case':<24}" + "".join(f"{name:<30}" for name in ORDERS)
    print(header)
    rows = {}
    for case_name, ctx in CASES.items():
        row = f"{case_name:<24}"
        rows[case_name] = {}
        for order_name, order in ORDERS.items():
            try:
                data = call_jev(ctx, order)
            except requests.HTTPError as exc:
                body = exc.response.text[:200] if exc.response is not None else str(exc)
                row += f"{'HTTP ' + str(exc.response.status_code) + ': ' + body:<30}"
                rows[case_name][order_name] = {"error": body}
                time.sleep(0.3)
                continue
            answers = data.get("answers", {})
            tier = answers.get("risk_tier", {})
            risky = answers.get("is_risky", {})
            choice = tier.get("choice", "ERR")
            conf = tier.get("confidence")
            conf_s = f"{conf:.3f}" if conf is not None else "n/a"
            cell = f"{choice}(c={conf_s})"
            row += f"{cell:<30}"
            rows[case_name][order_name] = {
                "risk_tier_choice": choice,
                "risk_tier_confidence": conf,
                "is_risky": risky.get("noul"),
                "response_model": data.get("model"),
            }
            time.sleep(0.3)
        print(row)
    print()
    return rows


def main():
    started = datetime.datetime.now(datetime.timezone.utc)
    passes = {f"pass_{n}": run_pass(n) for n in (1, 2)}

    print("Same-order repeat control (pass 1 vs pass 2, max |confidence diff|):")
    for case_name in CASES:
        diffs = []
        for order_name in ORDERS:
            a = passes["pass_1"][case_name][order_name].get("risk_tier_confidence")
            b = passes["pass_2"][case_name][order_name].get("risk_tier_confidence")
            if a is not None and b is not None:
                diffs.append(abs(a - b))
        print(f"  {case_name:<24}{max(diffs):.4f}" if diffs else f"  {case_name:<24}n/a")
    print()
    print("Reading this: if the chosen tier stays the same across orderings,")
    print("reordering the criteria map did not change Jev's answer on these")
    print("cases. If same-order repeats are identical but orderings differ in")
    print("confidence, the order reached the model. This says nothing about why.")

    out = pathlib.Path(__file__).parent / "results" / (
        f"exp6_results_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    out.write_text(json.dumps(
        {"endpoint": ENDPOINT, "model": MODEL, "started_utc": started.isoformat(),
         "orders": ORDERS, "tier_descriptions": TIER_DESCRIPTIONS, "passes": passes},
        indent=2,
    ))
    print(f"\nRaw results written to {out.name}")


if __name__ == "__main__":
    main()
