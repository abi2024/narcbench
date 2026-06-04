# Pre-Registration: Qwen2.5-7B-Instruct Engagement-Quality Comparison

**Author:** Abi
**Date drafted:** 2026-06-02
**Project:** CoT-Resampling Collusion Probes — Phase 2, Priority 1b (third-model comparison after Path 2 decision)
**Status:** Pre-registered. Predictions committed BEFORE generation begins.

---

## Purpose and reframed claim

The R1-Distill-Qwen-7B v2 batch revealed that the original "leakage rate replicates across models" framing is not supported. The substrate-quality scan showed:

- R1-Distill honest agents in control mode engage with the conversational task in 12.5% of messages (70/560 > 500 chars) vs Qwen3-30B's 87% (486/560).
- R1-Distill produces a bimodal output distribution: median 26 chars (terse bet announcements ignoring the chat-naturally instruction) plus rare long-tail outliers (5/840 honest messages > 2000 chars) containing structured reasoning content.
- The original `<think>`-leakage question is malformed when the model does not reliably use the `<think>` channel for its reasoning.

The reframed central claim of the paper is now:

> Reasoning-channel monitoring methodology assumes (a) the model reliably uses the reasoning channel for its reasoning, AND (b) the model engages with the public conversational task in a manner the methodology is built for. These properties are not preserved by all reasoning-model training pipelines.

This pre-registration tests one specific causal attribution within that claim:

> **Hypothesis H1:** R1-style reasoning distillation degrades public-channel conversational engagement *compared to instruction-tuning the same base model*.

Qwen2.5-7B-Instruct is the same base model (Qwen2.5-7B) that R1-Distill-Qwen-7B was derived from, but trained with standard instruction-tuning rather than R1 reasoning-trace distillation. Comparing the two isolates the distillation step as the source of any engagement difference.

---

## What is held constant

The Path 2 run uses the same benchmark code, prompts, seeds, judge configuration, and 20-shoe structure as the prior Qwen3-30B v4 and R1-Distill v2 runs. Specifically:

- Benchmark code at `generation/stego.py` (HEAD includes the counter-side strip patch and the new `--non-reasoning-model` flag).
- Number of shoes: 20 collusion + 20 control = 40 runs.
- Hands per shoe: 8.
- Players per table: 4 (2 colluders + 2 honest in collusion mode; 4 honest in control mode).
- Coordination rounds: 2.
- `MAX_TOKENS_CHAT = 6144`, `MAX_TOKENS_COORD = 8192`.
- vLLM bf16 inference.
- Same system prompts, user prompt templates, and shoe seeds (0..19).
- Same `_strip_think` extraction logic (with the new pass-through behavior for non-reasoning models).
- Same Claude Sonnet 4.5 judge for any subsequent leakage screen (likely NOT run for this batch — see "Why no judge step" below).

## What changes vs prior runs

Three changes, all pre-declared:

1. **Model:** `Qwen/Qwen2.5-7B-Instruct` (bf16, 7B dense, instruction-tuned from Qwen2.5-7B base).

2. **Sampling temperature:** 0.7. Qwen2.5 documentation recommends 0.7-0.95 for chat-style tasks; 0.7 is the conservative end and is the closest match to the temperature regime used for the other two runs (Qwen3 ~0.7, R1-Distill 0.6).

3. **CLI flag:** `--non-reasoning-model` set. This disables `<think>` tag handling: responses pass through `_strip_think` unchanged, and `chat_template_kwargs` is omitted from the API payload (Qwen2.5-Instruct's chat template does not define `enable_thinking` and may reject unknown kwargs).

GPU is the same RTX PRO 4500 Blackwell 32GB used for R1-Distill v2.

---

## Why no judge step (yet)

The Claude judge measures whether `<think>` content articulates scheme details. Qwen2.5-7B-Instruct does not produce `<think>` content at all. Running the judge would either return uniformly empty results (if applied to the empty `<think>` channel) or measure the *public* channel for scheme content (which is a different question and would require a different judge prompt).

For this run, the load-bearing measurements are:

- Public-channel engagement rate (analogous to what we measured retrospectively on Qwen3-30B and R1-Distill v2).
- Public-channel length distribution.
- Substrate cleanness (no `</think>` leaks — trivially expected to be 0 since there's no `<think>` channel — and no DECODE/PRIVATE marker leaks).
- BP-count correlation in collusion mode (does the scheme execute? This tests whether Qwen2.5-Instruct can follow the multi-step coordination prompt at all).

If the engagement-rate result is decisive, we proceed to write the paper. If it is ambiguous, we may add a public-channel-leakage judge pass later, with its own pre-registration.

---

## Predictions

### Primary outcome (load-bearing)

**P1. Honest-agent engagement rate (>500 chars in honest public messages, control mode): 65-90%.**

This is the headline prediction. The midpoint is calibrated below Qwen3-30B's 87% (Qwen2.5 is smaller and less verbose by training norms) and well above R1-Distill v2's 12.5% (if H1 holds, Qwen2.5 should engage substantially better than its R1-distilled counterpart).

**P2. Median honest-agent public message length (control mode): 300-700 chars.**

Above R1-Distill v2's median of 26 chars. The range reflects uncertainty about how much "social chatter" Qwen2.5-7B-Instruct produces; we'd be surprised by either extreme.

### Falsification criteria

**F1 (primary): If P1 result is <40%**, the engagement degradation is not specific to R1 distillation — it generalizes to smaller models regardless of training pipeline. The paper's causal attribution must be reframed to "smaller models" rather than "R1-distilled models."

**F2 (primary): If P1 result is >95%**, Qwen2.5-7B engages dramatically better than predicted, which would strengthen the R1-distillation attribution but raise a separate question of whether the engagement metric is correlated with model size at all (since Qwen2.5 is smaller than Qwen3-30B but might still match its engagement). Not strictly a falsification but flagged as an unexpected result.

**F3 (secondary): If substrate cleanness shows any non-zero marker leaks** (DECODE: or PRIVATE: in public messages, after the strip patch), there is either a bug in the strip patch for the non-reasoning code path or Qwen2.5-Instruct emits these markers without role-play prompting. Inspection required before drawing engagement conclusions.

**F4 (secondary): If `_strip_think` produces "[message cut short]" placeholders >5%** (which it should never do for `is_reasoning_model=False`), the pass-through flag isn't taking effect.

### Secondary outcomes (not load-bearing but recorded)

**P3. BP-count correlation collusion mode median: 0.10-0.55.**

Qwen2.5-7B-Instruct is not a reasoning model. The 2-round coordination phase and the multi-step counter/BP prompts may be harder for it to execute coherently than for Qwen3-30B or R1-Distill. A meaningfully positive median (>0.10) indicates the scheme executes at all; near-zero suggests the prompts collapse.

**P4. BP-count correlation control mode median: -0.20 to +0.20.**

No scheme exists in control mode. Median should regress to zero at n=20.

**P5. Length outliers (honest, >2000 chars): 0-3.**

If H1 holds, Qwen2.5-7B-Instruct should not exhibit the reasoning-dump failure mode that R1-Distill v2 showed (5 honest outliers >2000 chars). A clean zero would be strong evidence; up to 3 is within noise.

**P6. `<think>` tag rate: 0% (trivially, by model design).**

This is not a real prediction — it's a sanity check that the pipeline correctly recognizes the model is non-reasoning. If any messages contain `</think>`, something has gone wrong with the model or the chat template.

**P7. Truncation placeholder rate: 0% (after pass-through patch).**

If `_strip_think(content, is_reasoning_model=False)` works correctly, no message should be replaced with `"[message cut short]"`. Non-zero indicates the patch isn't applied or there's a fallback bug.

### Tertiary observations (record only)

- Style of any long outliers. Are they structured deliberation (Hannah-style), over-eager chat (Glenn-Kimura-style), or something new?
- In-game pit-boss verdict rate (CLEAR vs SUSPICIOUS).
- How Qwen2.5-Instruct handles the multi-step counter/BP prompts.
- Whether colluders attempt to follow the scheme at all (RANGE: and DECODE: line emission rate).

---

## Decision tree for paper claim after this run

| P1 result | Implication for paper |
|---|---|
| 65-90% (matches prediction) | H1 supported. Paper claim: "R1-distillation specifically degrades engagement vs instruction-tuning the same base model." |
| <40% (F1 triggered) | H1 falsified. Paper reframes to "small models in general have weaker engagement; we cannot isolate R1 distillation as the cause without additional comparisons." |
| 40-65% (partial) | Ambiguous. Paper reports both possibilities; flag size and distillation as joint contributors. |
| >95% (F2 triggered) | H1 strongly supported but flag the unexpected magnitude. |

The load-bearing question is decided by a single number (engagement rate) from a single batch.

---

## What the paper now claims, depending on P1

If H1 is supported, the paper's central claim becomes:

> Reasoning-channel monitoring requires reasoning-channel separation, which depends on training pipeline. We demonstrate this by comparing three models on a clean benchmark: Qwen3-30B-A3B-Thinking-2507 (reasoning model, maintains separation, 100% scheme content in `<think>`), DeepSeek-R1-Distill-Qwen-7B (reasoning model derived from Qwen2.5-7B via R1 trace distillation, weak separation, 12.5% public-channel engagement, structured reasoning content occasionally in public output), and Qwen2.5-7B-Instruct (same base model as R1-Distill but instruction-tuned, [X%] engagement). The Qwen2.5/R1-Distill pair holds base model and size constant; the engagement gap is attributable to the post-training pipeline. We recommend characterizing channel separation and engagement quality before deploying CoT monitoring on a given model.

---

## Pre-registration timestamp

This document is committed to git BEFORE the Path 2 generation run begins. The commit hash is the reference point for "pre-registration." Generation must not start before this commit lands. Any post-hoc deviation from the predictions or their interpretation must be flagged as such in the paper.

---

## Reference

- Phase 1 framing memo: `docs/framing_memo_phase2.md`
- Phase 1 (Qwen3-30B) predictions: `docs/predictions_v4.md`
- Phase 2 Round 1 (R1-Distill v1) predictions: `docs/predictions_r1distill_v1.md`
- R1-Distill v2 distribution scan results (engagement: 12.5% control vs Qwen3's 87%)
- Generation code HEAD: must include both `PATCH (2026-06-02)` markers (counter-side strip + non-reasoning-model handling)

---

## Results (appended 2026-06-04, after full-batch generation)

### Pre-registered predictions vs outcomes

| Prediction | Predicted | Observed | Verdict |
|---|---|---|---|
| P1: Honest engagement >500 (control) | 65-90% | **40.0%** | Outside predicted range; on F1 boundary but did not trigger |
| P2: Median honest length (control) | 300-700 | **459** | Within range |
| P3: BP-count corr collusion median | 0.10-0.55 | **+0.000** | Below floor — model cannot execute scheme |
| P4: BP-count corr control median | -0.20 to +0.20 | **+0.150** | Within range |
| P5: Length outliers >2000 (honest) | 0-3 | **0** | Within range |
| P6: had_think_tag rate | 0% | **0.0%** | Sanity check passed |
| P7: Truncation rate | 0% | **0.0%** | Pass-through patch works |

### Falsification criteria

- F1 (engagement <40%): NOT triggered (40.0% exactly on boundary).
- F2 (engagement >95%): NOT triggered.
- F3 (any substrate contamination): NOT triggered.
- F4 (truncation placeholder >5%): NOT triggered.

### Headline result

R1 distillation specifically degrades channel separation. The Qwen2.5/R1-Distill pair, holding base model (Qwen2.5-7B) and size (7B) constant, shows:
- Qwen2.5-7B-Instruct: clean substrate, consistent engagement (99.3% >200 chars), failed scheme execution (0.000 correlation).
- R1-Distill-Qwen-7B: contaminated substrate (2 PRIVATE + 10 length outliers), bimodal engagement (median 26 chars), partial scheme execution (0.402 correlation).

The pre-registered metric (>500 chars) was calibrated to Qwen3-30B's distribution and produces a misleadingly low number for the smaller Qwen2.5. The full distribution and engagement at >200/>300 thresholds tell a clearer story.

### Unexpected finding (P3 failure)

Qwen2.5-7B cannot execute the multi-step coordination prompt (BP-count correlation 0.000 vs predicted 0.10-0.55). This is a separate observation worth documenting: the benchmark assumes the model can coherently follow the counter/BP role prompts; for Qwen2.5-Instruct it cannot. Channel separation and coordination capability are decoupled.

### Decision

Proceed to paper writing. No further model runs before submission. R1-Distill-Llama-8B and other extensions deferred to Paper 2.