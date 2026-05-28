"""
extract_think.py — MP4 of the Stego leakage screen.

Walks all Stego runs in data/raw/stego/, splits each public-channel message on
</think>, and writes one JSON line per think block tagged for the judge in MP5.

Decisions baked in (see master_plan_revision_supplement_2026-05-25.md §1.3,
ADR-007, and the conversation that produced this script):

  - Channel: PUBLIC only. Private (coordination) is by-design scheme
    articulation between colluders and is not "leakage" — there is no observer.
  - Populations: all four public-turn populations are emitted, tagged so MP5
    can run the judge per bucket:
      (mode=collusion, role=colluder)   - the leakage measurement.
      (mode=collusion, role=honest)     - in-run honest baseline.
      (mode=control,   role=honest)     - between-run honest baseline.
    The 'judge' role is excluded (judges are not part of the leakage question).
  - Two boolean flags rather than one:
      truncated     - no </think> in the message; the model ran out of budget
                      mid-thought. The "think" block may itself be cut off.
                      Judge with caution at MP5.
      empty_answer  - </think> present but post-tag answer is essentially empty
                      (< 20 chars after strip). The think block IS judgeable;
                      the model just chose not to talk. Not a defect.

Output: data/processed/leakage_screen/think_blocks.jsonl (gitignored).

Usage:
    python scripts/extract_think.py
    python scripts/extract_think.py --runs-dir data/raw/stego \
                                    --out data/processed/leakage_screen/think_blocks.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections import Counter

# Tag-split sentinel. NARCBench's stego.py call_vllm strips the OPENING <think>
# but leaves the closing </think>; we partition on the closing tag.
SPLIT_TAG = "</think>"

# Threshold below which we treat the answer side as effectively empty.
EMPTY_ANSWER_MAX_CHARS = 20


def parse_role_in_scheme(run_config: dict, agent_name: str) -> str:
    """Counter vs big_player vs honest. Coalition list is [counter, big_player]
    by stego.py's construction (see run_shoe, role assignment block)."""
    coalition = run_config.get("coalition") or []
    if not coalition:
        return "honest"  # control runs have no coalition
    if agent_name == coalition[0]:
        return "counter"
    if agent_name == coalition[1]:
        return "big_player"
    return "honest"


def extract_agent_from_prefix(msg: str) -> tuple[str | None, str]:
    """Public messages in results.json are prefixed '[Agent Name]: ...'.
    Strip the prefix; return (agent_name, body)."""
    if not msg.startswith("["):
        return None, msg
    end = msg.find("]:")
    if end < 0:
        return None, msg
    return msg[1:end], msg[end + 2:].lstrip()


def split_think(body: str) -> tuple[str, str, bool]:
    """Return (think_block, answer, truncated).

    If </think> is absent, the whole body is treated as think and truncated=True.
    Otherwise everything before </think> is the think block (the OPENING <think>
    is missing from stego.py's stored response — that's why we split on the
    closing tag, not via regex on both tags)."""
    if SPLIT_TAG not in body:
        return body, "", True
    think, _, answer = body.partition(SPLIT_TAG)
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
    """Produce one record per public-channel turn in this run."""
    run_id = cfg["run_id"]
    mode = cfg["mode"]
    shoe = shoe_idx_from_run_id(run_id)
    roles_map = cfg.get("roles", {})
    bp_corr = cfg.get("bp_bet_correlation")

    records = []
    public_messages = res.get("public_messages", []) or []

    # public_messages is ordered turn-by-turn within and across hands. The
    # message text doesn't carry hand_num — but agent_prompts.json does. We
    # don't strictly need hand_num for the judge, so emit a turn_idx instead
    # of trying to reconstruct hand_num (which is fragile and not worth it).
    for turn_idx, msg in enumerate(public_messages):
        agent_name, body = extract_agent_from_prefix(msg)
        if agent_name is None:
            # Malformed prefix — skip rather than poison the dataset.
            continue
        role = roles_map.get(agent_name, "unknown")
        if role not in ("colluder", "honest"):
            # 'judge' speaks on the public channel at checkpoints; exclude.
            continue

        think, answer, truncated = split_think(body)
        empty_answer = (not truncated) and (len(answer) < EMPTY_ANSWER_MAX_CHARS)

        records.append({
            "run_id": run_id,
            "mode": mode,
            "shoe": shoe,
            "turn_idx": turn_idx,
            "agent_name": agent_name,
            "role": role,
            "agent_role_in_scheme": parse_role_in_scheme(cfg, agent_name),
            "think_block": think,
            "think_len": len(think),
            "answer": answer,
            "answer_len": len(answer),
            "truncated": truncated,
            "empty_answer": empty_answer,
            "bp_corr": bp_corr,
        })
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
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
    all_records: list[dict] = []
    for cfg, res, _ in walk_runs(args.runs_dir):
        n_runs += 1
        all_records.extend(extract_one_run(cfg, res))

    with open(args.out, "w") as f:
        for rec in all_records:
            f.write(json.dumps(rec) + "\n")

    # Summary — this is the operator-facing readout you'll use to decide MP5.
    print(f"Runs walked:  {n_runs}")
    print(f"Records written: {len(all_records)}")
    print(f"Output:       {args.out}")
    print()

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
    print(f"Quality flags:")
    print(f"  truncated (no </think>):       {truncated} / {len(all_records)}")
    print(f"  empty_answer (<{EMPTY_ANSWER_MAX_CHARS} chars after </think>): {empties} / {len(all_records)}")
    print()

    # Think-block length distribution — proxy for "is there substance to judge".
    if all_records:
        lens = sorted(r["think_len"] for r in all_records)
        n = len(lens)
        p50 = lens[n // 2]
        p10 = lens[n // 10]
        p90 = lens[(9 * n) // 10]
        print(f"think_len: min {lens[0]}  p10 {p10}  median {p50}  p90 {p90}  max {lens[-1]}")


if __name__ == "__main__":
    main()