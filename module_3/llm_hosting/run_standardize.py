"""
run_standardize.py
-------------------

Driver script that adapts the instructor-provided app.py to our actual
scraped data shape, and parallelizes it across CPU cores as recommended
in the assignment instructions. app.py itself is used unmodified.

WHY THIS EXISTS
================
app.py's _call_llm() -- and the SYSTEM_PROMPT / FEW_SHOTS / sample_data.json
it ships with -- all assume each row's "program" field is a single COMBINED
string, e.g. "Information Studies, McGill University". That was the older
Grad Cafe data shape.

The current Grad Cafe site (and therefore scrape.py / clean.py in this
project) already reports School and Program as two SEPARATE fields --
confirmed against live captured HTML earlier in this project, not assumed.
Feeding cleaned_applicant_data.json straight into `python app.py --file ...`
would silently produce garbage: _call_llm would look only at the (now
university-less) "program" string, find no comma to split on, and mark
every single row's university "Unknown".

This script bridges that gap without touching app.py:
  1. For each row, it temporarily reconstructs the "Program, University"
     combined string app.py's prompt/few-shots/fallback parser expect.
  2. It calls app.py's own _call_llm() on that reconstruction.
  3. It attaches the resulting llm-generated-program /
     llm-generated-university fields back onto the ORIGINAL row, leaving
     program / university / raw_program_text exactly as clean.py produced
     them -- per the assignment's "preserve the original program name"
     requirement.

PARALLELIZATION
================
app.py's own --file mode processes rows one at a time, single-threaded --
impractically slow at 30,000+ rows (the assignment instructions
explicitly recommend parallelizing across your CPU cores). A single
loaded llama.cpp model isn't safe to call concurrently from multiple
threads sharing one context, so this uses process-based parallelism
instead: each worker process loads its OWN private copy of the model and
churns through an independent shard of rows. `llm_app.N_THREADS` is set
directly inside each worker (not via the N_THREADS env var) so it takes
effect correctly regardless of whether Python's multiprocessing start
method is "fork" or "spawn" on your OS.

Usage:
    python run_standardize.py \
        --in ../cleaned_applicant_data.json \
        --out ../llm_extend_applicant_data.json \
        --workers 4
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
from pathlib import Path
from typing import Any


def _combined_program_text(row: dict[str, Any]) -> str:
    """Reconstruct the "Program, University" string app.py expects, from
    our already-separate program/university fields. Falls back to
    whichever of the two is present if only one is.
    """
    program = (row.get("program") or row.get("raw_program_text") or "").strip()
    university = (row.get("university") or "").strip()
    if program and university:
        return f"{program}, {university}"
    return program or university


def _process_shard(rows: list[dict[str, Any]], n_threads: int) -> list[dict[str, Any]]:
    """Runs inside one worker process: import app.py fresh in this
    process, point it at a private model instance, then process this
    shard's rows sequentially against it.
    """
    import app as llm_app  # the instructor-provided module, unmodified

    llm_app.N_THREADS = n_threads  # override per-worker, see module docstring

    out = []
    for row in rows:
        combined = _combined_program_text(row)
        result = llm_app._call_llm(combined)
        new_row = dict(row)  # never mutate program/university/raw_program_text
        new_row["llm-generated-program"] = result["standardized_program"]
        new_row["llm-generated-university"] = result["standardized_university"]
        out.append(new_row)
    return out


def _chunk(seq: list, n: int) -> list[list]:
    """Split `seq` into at most `n` roughly-equal contiguous shards."""
    if n <= 1 or len(seq) <= 1:
        return [seq]
    size = max(1, -(-len(seq) // n))  # ceil division
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", default="../cleaned_applicant_data.json")
    parser.add_argument("--out", dest="out_path", default="../llm_extend_applicant_data.json")
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, min(4, (os.cpu_count() or 2))),
        help="worker processes (each loads its own copy of the model -- "
        "watch RAM if you go high; default is conservative)",
    )
    args = parser.parse_args()

    rows = json.loads(Path(args.in_path).read_text(encoding="utf-8"))
    if not rows:
        print(f"No rows found in {args.in_path} -- nothing to do.")
        Path(args.out_path).write_text("[]", encoding="utf-8")
        return

    n_workers = max(1, min(args.workers, len(rows)))
    shards = _chunk(rows, n_workers)
    threads_per_worker = max(1, (os.cpu_count() or 2) // max(1, len(shards)))

    print(
        f"Processing {len(rows)} rows across {len(shards)} worker process(es) "
        f"({threads_per_worker} llama.cpp thread(s) each)..."
    )

    with mp.Pool(processes=len(shards)) as pool:
        results = pool.starmap(
            _process_shard, [(shard, threads_per_worker) for shard in shards]
        )

    combined_out = [row for shard_result in results for row in shard_result]
    Path(args.out_path).write_text(
        json.dumps(combined_out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {len(combined_out)} records to {args.out_path}")


if __name__ == "__main__":
    main()
