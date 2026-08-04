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


def load_seen() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        return set(json.loads(STATE_FILE.read_text()).get("process_ids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen(ids: set[str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(
            {
                "updated": datetime.now(timezone.utc).isoformat(),
                "process_ids": sorted(ids),
            },
            indent=2,
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
    seen = load_seen()

    pid_field = config.FIELDS["process_id"]
    new_ids = {r.get(pid_field) for r in candidates if r.get(pid_field) not in seen}
    new_ids.discard(None)

    print(f"Candidates after filtering: {len(candidates)}")
    print(f"New since last run: {len(new_ids)}")

    if not candidates:
        print("Nothing matched. No email sent.")
        return 0

    # Only send if something is actually new. Otherwise the recipient gets the
    # same five processes every morning and stops reading within a week.
    if not new_ids and not dry_run:
        print("No new processes today. Skipping send.")
        return 0

    # Put new processes first so the model sees them at the top of the list.
    candidates.sort(key=lambda r: r.get(pid_field) not in seen)

    selected = rank.rank(candidates)
    if not selected:
        print("Ranking returned nothing. No email sent.")
        return 0

    stats = {
        "scanned": len(candidates),
        "candidates": len(candidates),
        "new": len(new_ids),
    }
    html_body = report.render(selected, stats)

    if dry_run:
        pathlib.Path("preview.html").write_text(html_body, encoding="utf-8")
        print("Wrote preview.html. Open it in a browser.")
        return 0

    today = datetime.now(BOGOTA).strftime("%d/%m/%Y")
    report.send(html_body, f"Oportunidades SECOP II - Region Caribe - {today}")
    save_seen(seen | {r.get(pid_field) for r in candidates if r.get(pid_field)})
    print(f"Sent {len(selected)} opportunities.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
