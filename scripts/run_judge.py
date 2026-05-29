"""
run_judge.py — MP5 of the Stego leakage screen.

Reads think_blocks.jsonl, calls the judge model once per block, writes a
results JSONL incrementally. Resume-safe: re-running skips blocks whose
record_id already appears in the output file.

The judge prompts (B1a naive-observer, B1b scheme-aware) live in
scripts/judge_prompts.py. This file is the harness only.

Modes:
  --mode colluder      Judge collusion-mode counter + big_player blocks.
                       This is the leakage measurement population (~275 records
                       after excluding truncated colluder blocks).
  --mode honest-sample Judge a random sample of honest blocks. Run FIRST to
                       calibrate: their gratuitous-disclosure rate must be ~0%.
  --mode all           Everything. Use sparingly — expensive.

Prompt variant:
  --prompt b1a   (default) Judge sees think block ONLY. The threat model:
                  a naive observer with no knowledge of any scheme.
  --prompt b1b   Judge sees think block + a description of what kind of scheme
                  exists. Cross-check for sensitivity, not the headline measure.

Discipline:
  --limit N      Only judge N blocks. Use --limit 5 FIRST to read judgments by
                 hand before any full run.
  --seed S       For reproducible sampling (default 42).

Truncated colluder blocks are excluded automatically — their think may be cut
mid-thought, judge result not trustworthy. Logged but not judged.

Usage:
  # Sanity check — 5 colluder blocks, read by hand:
  python scripts/run_judge.py --mode colluder --limit 5

  # Calibration — 100 honest blocks. Must score near 0% gratuitous.
  python scripts/run_judge.py --mode honest-sample --n 100

  # The actual measurement, after calibration passes:
  python scripts/run_judge.py --mode colluder

  # Cross-check on a colluder sample with the scheme-aware prompt:
  python scripts/run_judge.py --mode colluder --prompt b1b --limit 50

Outputs:
  data/processed/leakage_screen/judge_results.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Iterator

import anthropic

from judge_prompts import build_b1a_prompt, build_b1b_prompt, SCHEME_DESCRIPTION

JUDGE_MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 800
DEFAULT_INPUT = Path("data/processed/leakage_screen/think_blocks.jsonl")
DEFAULT_OUTPUT = Path("data/processed/leakage_screen/judge_results.jsonl")


def make_record_id(block: dict) -> str:
    """Stable per-block id used for resume-skip."""
    return f"{block['run_id']}::{block['phase']}::r{block['round']}::{block['agent_name']}"


def load_blocks(path: Path) -> list[dict]:
    """Load think_blocks.jsonl into memory. ~1100 small records — fine."""
    return [json.loads(line) for line in path.open()]


def already_judged(output_path: Path) -> set[str]:
    """Read any existing judge_results.jsonl and return record_ids already done.
    Skips lines that aren't valid JSON or lack record_id — robust to partial writes."""
    done = set()
    if not output_path.exists():
        return done
    for line in output_path.open():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if "record_id" in rec:
                done.add(rec["record_id"])
        except json.JSONDecodeError:
            continue
    return done


def filter_for_mode(blocks: list[dict], mode: str, n: int, seed: int) -> list[dict]:
    """Select the population for this run."""
    if mode == "colluder":
        sel = [b for b in blocks
               if b["mode"] == "collusion"
               and b["role"] == "colluder"
               and not b["truncated"]]
        return sel

    if mode == "honest-sample":
        # Sample from both in-run honest (collusion-mode) and between-run honest
        # (control-mode). Stratify to keep the calibration honest.
        in_run = [b for b in blocks
                  if b["mode"] == "collusion" and b["role"] == "honest"
                  and not b["truncated"]]
        between = [b for b in blocks
                   if b["mode"] == "control" and b["role"] == "honest"
                   and not b["truncated"]]
        rng = random.Random(seed)
        half = n // 2
        sample = rng.sample(in_run, min(half, len(in_run))) + \
                 rng.sample(between, min(n - half, len(between)))
        rng.shuffle(sample)
        return sample

    if mode == "all":
        return [b for b in blocks if not b["truncated"]]

    raise ValueError(f"Unknown mode: {mode}")


def call_judge_with_retry(client: anthropic.Anthropic,
                           system: str,
                           user: str,
                           max_retries: int = 5) -> dict:
    """Call the judge, parse JSON output, retry on transient errors.

    Returns a dict with 'raw_text', 'parsed' (or None), 'error' (or None)."""
    for attempt in range(max_retries):
        try:
            resp = client.messages.create(
                model=JUDGE_MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = resp.content[0].text
            # Try to parse JSON. Models sometimes wrap in ```json fences.
            stripped = text.strip()
            if stripped.startswith("```"):
                # Strip ```json ... ``` fences if present
                lines = stripped.split("\n")
                stripped = "\n".join(line for line in lines if not line.startswith("```"))
            try:
                parsed = json.loads(stripped)
                return {"raw_text": text, "parsed": parsed, "error": None}
            except json.JSONDecodeError as e:
                return {"raw_text": text, "parsed": None,
                        "error": f"JSONDecodeError: {e}"}

        except anthropic.RateLimitError as e:
            wait = 2 ** attempt
            print(f"  rate limit, sleeping {wait}s...", flush=True)
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            # Non-retriable for most status codes — bail loudly.
            if e.status_code in (529, 503, 502, 500):
                wait = 2 ** attempt
                print(f"  api {e.status_code}, sleeping {wait}s...", flush=True)
                time.sleep(wait)
                continue
            return {"raw_text": "", "parsed": None,
                    "error": f"APIStatusError {e.status_code}: {e}"}
        except Exception as e:
            return {"raw_text": "", "parsed": None,
                    "error": f"{type(e).__name__}: {e}"}

    return {"raw_text": "", "parsed": None,
            "error": "max_retries exhausted"}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["colluder", "honest-sample", "all"],
                        required=True)
    parser.add_argument("--prompt", choices=["b1a", "b1b"], default="b1a")
    parser.add_argument("--n", type=int, default=100,
                        help="Sample size for honest-sample mode (default 100).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap blocks judged. Use --limit 5 for dry-runs.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-resume", action="store_true",
                        help="Re-judge blocks already in --output (writes duplicates).")
    args = parser.parse_args()

    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("ANTHROPIC_API_KEY not set.")

    if not args.input.exists():
        sys.exit(f"Input not found: {args.input}")

    args.output.parent.mkdir(parents=True, exist_ok=True)

    blocks = load_blocks(args.input)
    print(f"Loaded {len(blocks)} blocks from {args.input}")

    selected = filter_for_mode(blocks, args.mode, args.n, args.seed)
    print(f"Mode: {args.mode}  | Population: {len(selected)} blocks")

    if args.limit:
        selected = selected[:args.limit]
        print(f"Limit: {args.limit}  | Will judge: {len(selected)}")

    # Resume
    done = set() if args.no_resume else already_judged(args.output)
    if done:
        print(f"Resume: {len(done)} record_ids already in {args.output}, will skip.")
    to_judge = [b for b in selected if make_record_id(b) not in done]
    print(f"To judge: {len(to_judge)}")

    if not to_judge:
        print("Nothing to do. Exit.")
        return

    client = anthropic.Anthropic()

    # Open output in append mode so each judgment writes immediately. A crash
    # mid-run loses only the in-flight block; resume picks up the rest.
    n_ok = 0
    n_parse_fail = 0
    n_error = 0

    with args.output.open("a") as out_f:
        for i, block in enumerate(to_judge):
            rid = make_record_id(block)
            think = block["think_block"]

            if args.prompt == "b1a":
                system, user = build_b1a_prompt(think)
            else:
                system, user = build_b1b_prompt(think, SCHEME_DESCRIPTION)

            result = call_judge_with_retry(client, system, user)

            out_rec = {
                "record_id": rid,
                "prompt_variant": args.prompt,
                "judge_model": JUDGE_MODEL,
                # Carry the block's metadata so scoring is self-contained.
                "run_id": block["run_id"],
                "mode": block["mode"],
                "role": block["role"],
                "agent_role_in_scheme": block["agent_role_in_scheme"],
                "phase": block["phase"],
                "round": block["round"],
                "shoe": block["shoe"],
                "bp_corr": block["bp_corr"],
                "think_len": block["think_len"],
                # Judge output.
                "grade": result["parsed"].get("grade") if result["parsed"] else None,
                "reconstructable_elements": (
                    result["parsed"].get("reconstructable_elements")
                    if result["parsed"] else None
                ),
                "reasoning": (
                    result["parsed"].get("reasoning") if result["parsed"] else None
                ),
                "raw_text": result["raw_text"],
                "error": result["error"],
            }
            out_f.write(json.dumps(out_rec) + "\n")
            out_f.flush()
            os.fsync(out_f.fileno())  # paranoia — the network FS has bitten us

            if result["error"]:
                n_error += 1
                status = f"ERROR ({result['error'][:60]})"
            elif result["parsed"] is None:
                n_parse_fail += 1
                status = "PARSE-FAIL"
            else:
                n_ok += 1
                status = f"grade={result['parsed'].get('grade')}"

            print(f"[{i+1}/{len(to_judge)}] {rid}  {status}", flush=True)

    print()
    print(f"Done. OK: {n_ok}  | parse-fail: {n_parse_fail}  | error: {n_error}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()