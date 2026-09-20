# The interface is easy to copy. Position invariance isn't.

![Shuffle the options. The clone follows the slot. Jev follows the label.](figure/jev-position-sensitivity.png)

TypeSafe launched Jev on 15 September 2026. Instead of generating text and parsing JSON out of it, you send typed questions over a fixed answer space (boolean, enum, score) plus context, and get what TypeSafe describes as a calibrated probability per field back in one forward pass. TypeSafe claims 40-200x speed and cost advantages over generate-then-parse, and near-zero hallucination by construction: the output space is constrained, so the model can't emit a value outside your schema.

Within days, open-source clones of the interface showed up. They read logits at constrained answer positions on local open-weight models instead of generating tokens: same interface shape, none of TypeSafe's training behind it. I ran one of them, jevmlx (MLX-native, Qwen2.5-1.5B-Instruct-4bit, fully local), against a small position-sensitivity test, then ran the same test against real Jev to see whether the gap between "looks like Jev" and "is Jev" shows up somewhere concrete.

It does, in one specific place: how stable the answer is to the order you list your enum options in.

## The test

Six short messages, one boolean field (`is_risky`) and one 3-option enum field (`risk_tier`: low/medium/high), run through three different orderings of the same three options: `[low, medium, high]`, `[high, medium, low]`, `[medium, high, low]`. Same option descriptions in every ordering, only the position in the prompt/criteria map changes, never the meaning.

If a model's answer is a genuine read of the case, the chosen tier shouldn't depend on where in the list the words happen to sit. If it does, something in the readout is leaking position into the decision.

Cases:

- `clear_high_risk_scam`: a phishing-style urgent message asking for card details
- `benign_smalltalk`: a coffee catch-up message
- `ambiguous_urgent`: a wire transfer request with no verification, urgent tone
- `technical_neutral`: a sensor reading within normal range
- `mild_concern`: an unrecognized small charge, plausibly a forgotten subscription
- `empty_string`: literally nothing

## jevmlx (local)

| case | orig (low/med/high) | reversed (high/med/low) | rotated (med/high/low) |
|---|---|---|---|
| clear_high_risk_scam | high | medium | high |
| benign_smalltalk | medium | medium | high |
| ambiguous_urgent | medium | medium | high |
| technical_neutral | low | low | low |
| mild_concern | medium | medium | high |
| empty_string | medium | medium | high |

5 of 6 cases change their answer depending only on where the option sits in the list. `technical_neutral` is the one exception.

The pattern is sharper than "unstable": 14 of the 18 answers are whichever option is listed second. That's `medium` in the first two orderings and `high` in the third, which is why a coffee invite and an empty string come out "high risk" once `high` moves into slot two. The only answers not in slot two are `technical_neutral` (always `low`) and the scam case in the original ordering.

The clone doesn't signal that anything is off, either. `benign_smalltalk` lands on `high` with a log-score margin of 1.48 nats over the runner-up, about the same margin it gives the scam message. A confidence threshold would not catch these.

## Real Jev

Each ordering sent twice (pass 1 / pass 2), because JSON objects are unordered by spec and TypeSafe's docs don't say whether the order of the `criteria` map is kept. The repeat tells us whether the ordering actually reaches the model.

| case | orig (low/med/high) | reversed (high/med/low) | rotated (med/high/low) |
|---|---|---|---|
| clear_high_risk_scam | high (1.00 / 1.00) | high (1.00 / 1.00) | high (1.00 / 1.00) |
| benign_smalltalk | low (1.00 / 1.00) | low (0.99 / 0.99) | low (0.99 / 0.99) |
| ambiguous_urgent | high (0.75 / 0.71) | high (0.88 / 0.87) | high (0.84 / 0.87) |
| technical_neutral | low (1.00 / 1.00) | low (1.00 / 1.00) | low (1.00 / 1.00) |
| mild_concern | low (0.60 / 0.67) | low (0.46 / 0.54) | low (0.50 / 0.56) |
| empty_string | low (1.00 / 1.00) | low (0.99 / 0.99) | low (1.00 / 1.00) |

0 of 6 flips, in both passes: 36 of 36 answers keep the same label.

The ordering does reach the model. Confidence shifts with order more than it shifts between identical requests: `ambiguous_urgent` spreads 0.13 to 0.16 across orderings against at most 0.04 between repeats, and it is lowest in the original ordering in both passes. `benign_smalltalk` and `empty_string` repeat exactly, yet still differ by 0.01 between orderings. `mild_concern` is the noisiest case (0.08 between repeats, 0.13 to 0.14 across orderings). So Jev sees the reordering, moves its confidence a little, and keeps the same answer. It is also not deterministic: identical requests can return confidences up to 0.08 apart.

`empty_string` was sent as a true empty string to both systems and Jev accepted it without complaint, landing on `low` at full confidence.

## What this does and doesn't show

The claim that survives scrutiny: on a 3-option enum, an open-source approximation of the Jev interface gave position-dependent answers on 5 of 6 cases, landing on the second-listed option 14 of 18 times. Real Jev gave position-invariant answers on 6 of 6 (in two passes), under the same option text, the same case list, the same three orderings.

That's it. A few things this is deliberately not claiming:

- **Not a mechanism claim.** I know the local model's answer moves with position. I don't know if that's a token prior, a first-token tokenization quirk in how the aliases get encoded, or a middle-slot bias. I only ruled out "the model just likes the word medium," since the flips track slot position, not the literal string. Adding option descriptions, so both systems saw the same rubric instead of bare words on one side, didn't change the result. If anything the local model flipped on one more case with descriptions than without.
- **Not an RLCD claim.** I don't know that TypeSafe's training process specifically is what fixes this. Model scale, instruction tuning, their exact prompt template, and how they handle the criteria map are all live alternative explanations. Whatever's in their pipeline, it produces stability the copy doesn't have.
- **Not a latency or cost claim.** I'm not touching the 40-200x number here. A single local forward pass and a network call to a hosted API aren't comparable that way, and conflating them would be sloppy in exactly the way a technical reader would catch immediately.
- **n=6, no ground truth, one model size, one quantization, one enum width.** This is a method demonstration, not a benchmark. The useful part is the test itself: reorder your options, rerun, see if the answer moves. Anyone can run that in ten minutes against any constrained-decoding wrapper.

## Take from it what's actually there

The System One interface (typed questions in, a probability per field out) is straightforward to approximate once you know the shape: read logits at the constrained answer positions instead of generating tokens. Days after launch, that's exactly what happened. What doesn't come for free is whatever makes the answer insensitive to which slot an option happens to occupy. Whatever produces that isn't in the wiring.

---

## Setup

- **Clone:** jevmlx from [bnsd55/openjev](https://github.com/bnsd55/openjev) at commit `bcdb12c`, Qwen2.5-1.5B-Instruct-4bit, local on an M4 MacBook via MLX (mlx 0.32.2, mlx_lm 0.31.3). `ordered` flag off; option descriptions are rendered in the prompt. The readout is deterministic, so two runs gave identical output: that confirms reproducibility, not robustness.
- **Jev:** hosted `jev-latest` alias (responses report `jev-1.13.0`) via TypeSafe's `/v1/systemone` API, run 2026-09-20 14:47 UTC, every ordering sent twice.

## Reproduce

```bash
# Clone side (Apple Silicon, Python >= 3.12)
pip install "jevmlx @ git+https://github.com/bnsd55/openjev@bcdb12cb3e3726f1691849bfdb6fb099c15c1933"
python3 clone_jevmlx_position.py

# Jev side (needs a TypeSafe API key; the script never prints it)
pip install requests
export TYPESAFE_API_KEY=...
python3 jev_hosted_position.py
```

To test another constrained-decoding wrapper, keep the six cases and option text, change only the order, and see whether the answer moves.

## Files

- `clone_jevmlx_position.py`, `jev_hosted_position.py`: the two tests
- `results/clone-run-1.txt`, `results/clone-run-2.txt`: raw clone output (identical)
- `results/jev-run.txt`, `results/exp6_results_20260920T144708Z.json`: raw Jev output, both passes

Not affiliated with TypeSafe or the jevmlx authors. Personal experiment.
