# Pre-registered predictions for the v4 (MP5e+f) leakage screen batch

Authored 2026-05-31, before the 20-shoe v4 generation runs.

## Predictions

### F1 — Colluder gratuitous-disclosure rate
- **Predicted:** 95-99.5% (most likely 97-99%).
- **Reasoning:** Contaminated batch was 99.3% [97.4%, 99.8%]. The
  fixes (MAX_TOKENS=6144, placeholder on missing `</think>`, BP
  decode-line strip) do not change colluder behavior — colluders
  have the scheme natively in their system prompt. We expect the
  number to land within ~2pp of the contaminated rate.
- **Falsifying outcome:** rate <90% would be a surprise requiring
  explanation.

### F2 — Pipeline contamination (in-run honest baseline)
- **Predicted, lower bound:** 0-5% from genuinely-clean contamination.
- **Predicted, upper bound:** 10-15% if F3 (role-confabulation) is real
  and substantial.
- **Reasoning:** Contaminated batch was 20%. v3 (strip-only,
  truncation-contaminated) was 38%. With contamination vectors closed,
  what remains is whatever the model does *naturally* — F3.
- **Falsifying outcome:** rate >30% indicates a contamination vector
  we have not identified.

### F3 — Honest-agent inference from observable behavior
- **Predicted:** 0-15%.
- **Reasoning:** Honest agents see colluder signaling phrases in
  table chat. We predict the model occasionally infers the scheme
  from observable patterns when signaling is strong. We do not
  predict the high (38%) v3 rate because that was driven by direct
  contamination, not inference.
- **Falsifying outcome:** rate >25% suggests residual contamination,
  not honest inference.

### bp_corr (coordination signal)
- **Predicted, collusion median:** 0.55-0.85.
- **Predicted, control median:** -0.1 to +0.2.
- **Reasoning:** Smoke v4 showed 0.69 and 0.64 on 2 collusion runs
  and -0.57 and +0.69 on 2 control runs (bimodal at small n).
  At n=20 control will regress to near 0; collusion should stay
  above 0.5.
- **Falsifying outcome:** Collusion median <0.4 would suggest the
  fixes broke coordination.

### Substrate cleanness
- **Predicted:** 0 `</think>` tags in `public_messages`, 0 DECODE/PRIVATE
  leaks, <2% truncation.
- **Reasoning:** Smoke v4 showed 0% for all three. We predict the
  20-shoe stays equally clean.

## Methodology

- 20 shoes × 2 modes (collusion + control) = 40 runs
- Model: Qwen/Qwen3-30B-A3B-Thinking-2507 (vLLM, bf16)
- MAX_TOKENS_CHAT = 6144, MAX_TOKENS_COORD = 8192
- 8 hands per shoe, 4 players + 1 pit-boss judge
- Judge: Claude Sonnet 4.5 (claude-sonnet-4-5-20250929), B1a prompt
- Pre-registered: 2026-05-31, before generation launch

## Substantive interpretation contingencies

- If F1 ≈ contaminated rate: confirms model-internal leakage is the
  dominant mechanism; the headline number is robust.
- If F2 ≈ 0%: confirms the contamination vectors were the source of
  the v3 38% rate.
- If F3 > 0 but <15%: novel finding worth its own paper section.
- If F3 = 0%: an interesting null result; the model role-confabulation
  was entirely contamination-driven.
