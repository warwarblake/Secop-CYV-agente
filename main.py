#!/usr/bin/env python3
"""
Daily SECOP II opportunity report for CYV Constructora.

Usage:
    python main.py --inspect     Print the live column names from SECOP II.
                                 Run this FIRST, before anything else.
    python main.py --dry-run     Build the report and write preview.html.
                                 Does not send. Does not update state.
    python main.py               Build and send. Updates state/seen.json.
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

from src import config, rank, report, secop

STATE_FILE = pathlib.Path("state/seen.json")
BOGOTA = timezone(timedelta(hours=-5))


def load_seen() -> dict:
    """Returns {process_id: first_seen_date_iso}."""
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text()).get("process_ids", {})
    except (json.JSONDecodeError, OSError):
        return {}


def save_seen(seen: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(
            {
                "updated": datetime.now(timezone.utc).isoformat(),
                "process_ids": seen,
            },
            indent=2,
            sort_keys=True,
        )
    )


def do_inspect() -> int:
    print("Live columns in SECOP II dataset", config.DATASET_ID)
    print("(from dataset metadata, not a sampled row -- see comment in secop.py)")
    print("-" * 70)
    schema = secop.inspect_schema()
    field_names = {c["fieldName"] for c in schema}
    for c in schema:
        print(f"  {c['fieldName']:40s} | {c['name']}")
    print("-" * 70)

    print("\nColumns whose Spanish label mentions offers/deadline/reception ")
    print("(one of these should be your bid-submission-deadline field,")
    print("e.g. 'Presentacion de Ofertas'):\n")
    deadline_hints = [
        c for c in schema
        if c["name"] and any(
            term in secop.normalize(c["name"])
            for term in ["oferta", "presentacion", "recepcion", "cierre"]
        )
    ]
    if deadline_hints:
        for c in deadline_hints:
            print(f"  {c['fieldName']:40s} | {c['name']}")
    else:
        print("  (none found -- this dataset may not track that date at all)")

    print("\nChecking config.FIELDS against this schema:\n")
    ok = True
    for label, field in config.FIELDS.items():
        if field is None:
            print(f"  SKIPPED {label:12s} -> not mapped yet")
            continue
        if field in field_names:
            print(f"  OK      {label:12s} -> {field}")
        else:
            ok = False
            guesses = [c["fieldName"] for c in schema if field.split("_")[0] in (c["fieldName"] or "")][:3]
            hint = f"  did you mean: {', '.join(guesses)}" if guesses else ""
            print(f"  MISSING {label:12s} -> {field}{hint}")
    print()
    if not ok:
        print("Fix the MISSING entries in src/config.py before running.")
        return 1
    print("All field names match. You are ready to run.")
    return 0


def do_list_modalities() -> int:
    print("Sampling the last 90 days for your target departments...\n")
    modalities, types = secop.sample_modalities_and_types()

    print("Distinct MODALIDAD_DE_CONTRATACION values seen:")
    for m in sorted(modalities):
        flag = "  <-- matches REQUIRE_MODALITY" if any(
            t in secop.normalize(m) for t in [secop.normalize(x) for x in config.REQUIRE_MODALITY]
        ) else ""
        print(f"  {m}{flag}")

    print("\nDistinct TIPO_DE_CONTRATO values seen:")
    for t in sorted(types):
        flag = "  <-- matches REQUIRE_CONTRACT_TYPE" if any(
            x in secop.normalize(t) for x in [secop.normalize(y) for y in config.REQUIRE_CONTRACT_TYPE]
        ) else ""
        print(f"  {t}{flag}")

    print(
        "\nIf 'Licitacion Publica' / 'Obra' (or close variants) are not "
        "flagged above, update REQUIRE_MODALITY / REQUIRE_CONTRACT_TYPE in "
        "src/config.py to match exactly what's printed here."
    )
    return 0


def main() -> int:
    args = set(sys.argv[1:])

    if "--inspect" in args:
        return do_inspect()

    if "--list-modalities" in args:
        return do_list_modalities()

    dry_run = "--dry-run" in args

    candidates = secop.get_candidates()
    seen = load_seen()  # {process_id: first_seen_date_iso}

    pid_field = config.FIELDS["process_id"]
    today_str = datetime.now(BOGOTA).date().isoformat()

    # Rebuild state from scratch, keyed off TODAY's candidates only. Anything
    # not in today's candidate pool (closed, fell out of the lookback window,
    # no longer matches the filters) is simply not carried forward -- this
    # keeps the file from growing forever without needing separate cleanup.
    new_seen = {}
    newly_added_count = 0
    for row in candidates:
        pid = row.get(pid_field)
        if not pid:
            continue
        if pid in seen:
            new_seen[pid] = seen[pid]
        else:
            new_seen[pid] = today_str
            newly_added_count += 1
        row["_first_seen"] = new_seen[pid]

    print(f"Candidates after filtering: {len(candidates)}")
    print(f"New today: {newly_added_count}")

    if not candidates:
        print("Nothing matched. No email sent.")
        return 0

    # No longer gated on "something new today" -- a genuinely good match
    # should keep appearing in the top 5 for as long as it's still open and
    # still the best fit. Truly new candidates naturally compete for a spot
    # in the ranking below, so the list still shifts as new things appear or
    # old ones stop being the best 5.
    selected = rank.rank(candidates)
    if not selected:
        print("Ranking returned nothing. No email sent.")
        return 0

    stats = {
        "scanned": len(candidates),
        "candidates": len(candidates),
        "new": newly_added_count,
    }
    html_body = report.render(selected, stats)

    if dry_run:
        pathlib.Path("preview.html").write_text(html_body, encoding="utf-8")
        print("Wrote preview.html. Open it in a browser.")
        return 0

    today = datetime.now(BOGOTA).strftime("%d/%m/%Y")
    report.send(html_body, f"Oportunidades SECOP II - Region Caribe - {today}")
    save_seen(new_seen)
    print(f"Sent {len(selected)} opportunities.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
