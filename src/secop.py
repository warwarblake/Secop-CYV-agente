"""
SECOP II data access.

Design rule: the API and this module do ALL the filtering. The language model
never retrieves anything -- it only ranks and explains records that came back
from datos.gov.co. That way every process ID, value and deadline in the email
is traceable to a real API response field.
"""

from __future__ import annotations

import os
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

from . import config


# ---------------------------------------------------------------------------
# Text normalisation -- the fix for the accent problem
# ---------------------------------------------------------------------------

def normalize(text: str | None) -> str:
    """Lowercase and strip accents. 'Atlántico' -> 'atlantico'."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFD", str(text).lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").strip()


# ---------------------------------------------------------------------------
# API access
# ---------------------------------------------------------------------------

def _headers() -> dict:
    token = os.environ.get("SOCRATA_APP_TOKEN")
    return {"X-App-Token": token} if token else {}


def inspect_schema() -> list[dict]:
    """
    Fetch the dataset's real column list from Socrata's metadata endpoint.

    IMPORTANT: this deliberately does NOT sample a data row to infer columns.
    Socrata's JSON rows omit any field that's empty for that specific record,
    so a single sampled row can easily under-report the schema -- exactly
    what happened with the bid-deadline field, which just wasn't populated
    on the one process that got sampled. The metadata endpoint lists every
    column the dataset defines, regardless of what any individual row has.

    Returns a list of {"fieldName": ..., "name": ...} -- fieldName is what
    you use in SoQL queries and config.FIELDS; name is the human-readable
    label as it appears in SECOP's own UI, which is what you match against
    when you know a field by its Spanish name (e.g. "Presentacion de Ofertas").
    """
    url = f"{config.SOCRATA_DOMAIN}/api/views/{config.DATASET_ID}.json"
    resp = requests.get(url, headers=_headers(), timeout=60)
    resp.raise_for_status()
    columns = resp.json().get("columns", [])
    return sorted(
        [{"fieldName": c.get("fieldName"), "name": c.get("name")} for c in columns],
        key=lambda c: c["fieldName"] or "",
    )


def fetch_recent_processes() -> list[dict]:
    """
    Pull processes published in the lookback window above the price floor.

    Department filtering happens locally (see filter_by_department) so that
    accent and casing variants in the source data can never silently drop a
    department.
    """
    f = config.FIELDS
    since = (datetime.now(timezone.utc) - timedelta(days=config.LOOKBACK_DAYS)).strftime(
        "%Y-%m-%dT00:00:00.000"
    )

    where = (
        f"{f['published']} > '{since}' "
        f"AND {f['base_price']} > {config.MIN_BASE_PRICE_COP}"
    )

    url = f"{config.SOCRATA_DOMAIN}/resource/{config.DATASET_ID}.json"
    params = {
        "$where": where,
        "$limit": config.API_PAGE_LIMIT,
        "$order": f"{f['published']} DESC",
    }

    resp = requests.get(url, params=params, headers=_headers(), timeout=120)
    if resp.status_code == 400:
        raise RuntimeError(
            "SECOP returned 400. This almost always means a field name in "
            "config.FIELDS does not match the live schema. Run "
            "`python main.py --inspect` and correct config.FIELDS.\n\n"
            f"Query was: {where}\n\nResponse: {resp.text[:500]}"
        )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Local filtering
# ---------------------------------------------------------------------------

def filter_by_department(rows: list[dict]) -> list[dict]:
    targets = {normalize(d) for d in config.TARGET_DEPARTMENTS}
    field = config.FIELDS["department"]
    return [r for r in rows if normalize(r.get(field)) in targets]


def filter_by_relevance(rows: list[dict]) -> list[dict]:
    """Keep rows whose title or description looks like a civil works contract."""
    f = config.FIELDS
    include = [normalize(k) for k in config.RELEVANT_KEYWORDS]
    exclude = [normalize(k) for k in config.EXCLUDE_KEYWORDS]

    kept = []
    for row in rows:
        haystack = normalize(
            f"{row.get(f['title'], '')} {row.get(f['description'], '')}"
        )
        if any(term in haystack for term in exclude):
            continue
        hits = [term for term in include if term in haystack]
        if hits:
            row["_keyword_hits"] = hits[:6]
            kept.append(row)
    return kept


def filter_by_modality(rows: list[dict]) -> list[dict]:
    """
    Keep only Licitacion Publica processes whose contract type is Obra.

    This runs BEFORE the keyword filter, because it is the authoritative
    signal -- SECOP itself classifies the process, rather than us guessing
    from free text. If REQUIRE_MODALITY or REQUIRE_CONTRACT_TYPE is empty,
    that check is skipped (useful while you're still verifying field names).
    """
    f = config.FIELDS
    modality_targets = [normalize(m) for m in config.REQUIRE_MODALITY]
    type_targets = [normalize(t) for t in config.REQUIRE_CONTRACT_TYPE]

    out = []
    for row in rows:
        if modality_targets:
            modality = normalize(row.get(f["modality"]))
            if not any(t in modality for t in modality_targets):
                continue
        if type_targets:
            ctype = normalize(row.get(f["contract_type"]))
            if not any(t in ctype for t in type_targets):
                continue
        out.append(row)
    return out


def filter_open(rows: list[dict]) -> list[dict]:
    """
    Drop processes that are clearly closed or already awarded.

    Status vocabulary in SECOP II varies, so this is deliberately permissive:
    it only removes rows that explicitly say they are done.
    """
    field = config.FIELDS["status"]
    closed_markers = ["adjudicado", "celebrado", "terminado", "cancelado", "desierto"]
    out = []
    for row in rows:
        status = normalize(row.get(field))
        if any(m in status for m in closed_markers):
            continue
        out.append(row)
    return out


def filter_not_overdue(rows: list[dict]) -> list[dict]:
    """
    Drop any process whose bid-submission deadline has already passed.

    Only acts once config.FIELDS['closes'] is mapped to a real field --
    until then this is a no-op, since we have nothing reliable to check
    against and would rather show an unconfirmed date than wrongly drop
    a real opportunity.
    """
    field = config.FIELDS.get("closes")
    if not field or not config.EXCLUDE_OVERDUE:
        return rows

    now = datetime.now(timezone.utc)
    kept = []
    for row in rows:
        raw = row.get(field)
        if not raw:
            kept.append(row)  # no deadline on record -- keep, let Claudia verify
            continue
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except ValueError:
            kept.append(row)  # unparseable -- keep rather than silently drop
            continue
        if dt >= now:
            kept.append(row)
    return kept


def dedupe(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    key = config.FIELDS["process_id"]
    for row in rows:
        pid = row.get(key)
        if pid and pid not in seen:
            seen.add(pid)
            out.append(row)
    return out


def sample_modalities_and_types() -> tuple[set[str], set[str]]:
    """
    Pull a broad recent sample for the target departments and return the
    distinct raw values seen for modality and contract type. Use this to
    confirm REQUIRE_MODALITY / REQUIRE_CONTRACT_TYPE in config.py match
    what SECOP actually stores -- spelling and punctuation vary by entity.
    """
    f = config.FIELDS
    since = (datetime.now(timezone.utc) - timedelta(days=90)).strftime(
        "%Y-%m-%dT00:00:00.000"
    )
    url = f"{config.SOCRATA_DOMAIN}/resource/{config.DATASET_ID}.json"
    params = {
        "$where": f"{f['published']} > '{since}'",
        "$select": f"{f['modality']}, {f['contract_type']}, {f['department']}",
        "$limit": 20000,
    }
    resp = requests.get(url, params=params, headers=_headers(), timeout=120)
    resp.raise_for_status()
    rows = filter_by_department(resp.json())

    modalities = {r.get(f["modality"]) for r in rows if r.get(f["modality"])}
    types = {r.get(f["contract_type"]) for r in rows if r.get(f["contract_type"])}
    return modalities, types


def get_candidates() -> list[dict]:
    """Full pipeline: fetch -> department -> modality/type -> open -> not overdue -> relevance -> dedupe."""
    rows = fetch_recent_processes()
    rows = filter_by_department(rows)
    rows = filter_by_modality(rows)
    rows = filter_open(rows)
    rows = filter_not_overdue(rows)
    rows = filter_by_relevance(rows)
    return dedupe(rows)
