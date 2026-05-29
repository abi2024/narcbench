"""
extract_think.py — MP4/MP5e of the Stego leakage screen.

Walks all Stego runs in data/raw/stego/ and writes one JSON line per <think>
block tagged for the judge in MP5.

CHANGED (Path A, post-MP5c fix): reads `thinking_messages` directly. This is
the field populated by the patched stego.py's _call wrapper, which captures
the RAW model response (with <think>...</think> intact) into a per-call
record. We no longer parse public_messages for <think> content — that field
is now correctly clean (stripped) for downstream agent history.

Records in `thinking_messages` look like:
  {
    "agent_name": "Eduardo Reyes",
    "role": "colluder",
    "phase": "discussion" | "final" | "private",
    "channel": "public" | "private",
    "round": <hand_num or 0 for coord>,
    "raw_response": "<reasoning>...</think>\n<answer>",
    "had_think_tag": True | False,
  }

Decisions baked in (see master_plan_revision_supplement_2026-05-25.md §1.3,
ADR-007, ADR-009 in-progress):

  - Channel: PUBLIC only. Private (coordination) is by-design scheme
    articulation between colluders and is not "leakage" — there is no
    observer.
  - Populations: all four public-turn populations are emitted, tagged so MP5
    can run the judge per bucket:
      (mode=collusion, role=colluder)   - the leakage measurement.
      (mode=collusion, role=honest)     - in-run honest baseline.
      (mode=control,   role=honest)     - between-run honest baseline.
    The 'judge' role is excluded (judges are not part of the leakage
    question).
  - Two boolean flags:
      truncated     - no </think> in the raw_response; the model ran out of
                      budget mid-thought. The "think" block may itself be cut
                      off. Judge with caution at MP5.
      empty_answer  - </think> present but post-tag answer is essentially
                      empty (< 20 chars after strip). The think block IS
                      judgeable; the model just chose not to talk.

Output: data/processed/leakage_screen/think_blocks.jsonl (gitignored).

Usage:
    python scripts/extract_think.py
    python scripts/extract_think.py --runs-dir data/raw/stego \\
                                    --out data/processed/leakage_screen/think_blocks.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

SPLIT_TAG = "</think>"
EMPTY_ANSWER_MAX_CHARS = 20


def parse_role_in_scheme(run_config: dict, agent_name: str) -> str:
    """Counter vs big_player vs honest. Coalition list is [counter, big_player]
    by stego.py's construction."""
    coalition = run_config.get("coalition") or []
    if not coalition:
        return "honest"  # control runs have no coalition
    if agent_name == coalition[0]:
        return "counter"
    if agent_name == coalition[1]:
        return "big_player"
    return "honest"


def split_think(raw: str) -> tuple[str, str, bool]:
    """Return (think_block, answer, truncated).

    If </think> is absent, the whole raw response is treated as a think
    block and truncated=True. Otherwise everything before </think> is the
    think block (the OPENING <think> is consumed by vLLM's chat template,
    so we split on the closing tag alone).
    """
    if SPLIT_TAG not in raw:
        return raw, "", True
    think, _, answer = raw.partition(SPLIT_TAG)
    return think, answer.strip(), False


def shoe_idx_from_run_id(run_id: str) -> int | None:
    """run_id format: bj__shoe07__collusion. Pull the integer."""
    for part in run_id.split("__"):
        if part.startswith("shoe") and part[4:].isdigit():
            return int(part[4:])
    return None


def walk_runs(runs_dir: Path):
    """Yield (run_config, results, run_dir) for every run with all 3 files."""
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        cfg_path = run_dir / "run_config.json"
        res_path = run_dir / "results.json"
        if not (cfg_path.exists() and res_path.exists()):
            continue
        with open(cfg_path) as f:
            cfg = json.load(f)
        with open(res_path) as f:
            res = json.load(f)
        yield cfg, res, run_dir


def extract_one_run(cfg: dict, res: dict) -> list[dict]:
    """Produce one record per PUBLIC-channel thinking_messages entry."""
    run_id = cfg["run_id"]
    mode = cfg["mode"]
    shoe = shoe_idx_from_run_id(run_id)
    bp_corr = cfg.get("bp_bet_correlation")

    thinking = res.get("thinking_messages", []) or []
    if not thinking:
        # Old/contaminated runs predate the Path A fix and don't populate
        # this field. Skip rather than fall back — the contaminated batch
        # lives at data/raw/stego_contaminated_v1 and was already extracted.
        return []

    records = []
    for entry in thinking:
        # Filter: public channel only; colluder + honest roles only (skip
        # 'judge' role which speaks in public at checkpoints).
        if entry.get("channel") != "public":
            continue
        role = entry.get("role")
        if role not in ("colluder", "honest"):
            continue

        raw = entry.get("raw_response", "")
        agent = entry["agent_name"]
        think, answer, truncated = split_think(raw)
        empty_answer = (not truncated) and (len(answer) < EMPTY_ANSWER_MAX_CHARS)

        records.append({
            "run_id": run_id,
            "mode": mode,
            "shoe": shoe,
            "round": entry.get("round"),
            "phase": entry.get("phase"),
            "agent_name": agent,
            "role": role,
            "agent_role_in_scheme": parse_role_in_scheme(cfg, agent),
            "think_block": think,
            "think_len": len(think),
            "answer": answer,
            "answer_len": len(answer),
            "truncated": truncated,
            "empty_answer": empty_answer,
            "had_think_tag": entry.get("had_think_tag",
                                       SPLIT_TAG in raw),
            "bp_corr": bp_corr,
        })
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--runs-dir", type=Path,
        default=Path("data/raw/stego"),
        help="Directory containing bj__shoeNN__{collusion,control}/ run dirs.",
    )
    parser.add_argument(
        "--out", type=Path,
        default=Path("data/processed/leakage_screen/think_blocks.jsonl"),
        help="Output JSON-lines file.",
    )
    args = parser.parse_args()

    if not args.runs_dir.exists():
        sys.exit(f"Runs dir not found: {args.runs_dir}")

    args.out.parent.mkdir(parents=True, exist_ok=True)

    n_runs = 0
    n_runs_with_thinking = 0
    all_records: list[dict] = []
    for cfg, res, _ in walk_runs(args.runs_dir):
        n_runs += 1
        recs = extract_one_run(cfg, res)
        if recs:
            n_runs_with_thinking += 1
        all_records.extend(recs)

    with open(args.out, "w") as f:
        for rec in all_records:
            f.write(json.dumps(rec) + "\n")

    print(f"Runs walked:                {n_runs}")
    print(f"Runs with thinking_messages: {n_runs_with_thinking}")
    print(f"Records written:            {len(all_records)}")
    print(f"Output:                     {args.out}")
    print()

    if n_runs_with_thinking == 0:
        print("WARNING: no runs have a populated thinking_messages field.")
        print("This means the data was generated before the Path A stego.py")
        print("patch landed. Regenerate with the patched stego.py and re-run.")
        return

    by_bucket = Counter(
        (r["mode"], r["role"], r["agent_role_in_scheme"])
        for r in all_records
    )
    print("Distribution by (mode, role, role_in_scheme):")
    for key, n in sorted(by_bucket.items()):
        print(f"  {key}: {n}")
    print()

    truncated = sum(1 for r in all_records if r["truncated"])
    empties = sum(1 for r in all_records if r["empty_answer"])
    had_tag = sum(1 for r in all_records if r["had_think_tag"])
    print("Quality flags:")
    print(f"  had_think_tag (had </think>):  {had_tag} / {len(all_records)}")
    print(f"  truncated (no </think>):       {truncated} / {len(all_records)}")
    print(f"  empty_answer (<{EMPTY_ANSWER_MAX_CHARS} chars after </think>): {empties} / {len(all_records)}")
    print()

    if all_records:
        lens = sorted(r["think_len"] for r in all_records)
        n = len(lens)
        p10 = lens[n // 10]
        p50 = lens[n // 2]
        p90 = lens[(9 * n) // 10]
        print(f"think_len: min {lens[0]}  p10 {p10}  median {p50}  p90 {p90}  max {lens[-1]}")


if __name__ == "__main__":
    main()