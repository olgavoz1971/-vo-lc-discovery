"""Registry access (T-002). The only module that talks to the GAVO registry.

Offline collection for the local index (design 6.1): candidate routes, then
the coverage the registry declares. No per-star filter. Spectra vs lightcurves
are not separated here (T-003).

Every TAP call is printed and appended to discovery/logs/adql.log.
"""
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyvo as vo
from astropy.table import Table

REGISTRY_TAP = "http://reg.g-vo.org/tap"

# Project root: VO_lc_discovery/  (this file is vo-lc-discovery/src/vo_lc_discovery/)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOG_DIR = _PROJECT_ROOT / "discovery" / "logs"
ADQL_LOG = LOG_DIR / "adql.log"

# SSA services. The unit of discovery is the access URL; ivoid is a label.
# Also: the record's data tables (not 'output') and its auxiliary TAP endpoints.
# ivoa.obscore is dropped for now: it is shared, a route needs a
# dataproduct_type / dataproduct_subtype filter first (todo T-003).
# (ref_system_name NULL on rr.stc_spatial means ICRS; we do not filter on it here.)
QUERY_SSA = """
SELECT DISTINCT r.ivoid, r.res_title, c.cap_index, i.access_url,
       t.table_name, ai.access_url AS aux_tap_url
FROM rr.resource AS r
JOIN rr.capability AS c ON c.ivoid = r.ivoid
JOIN rr.interface AS i ON i.ivoid = c.ivoid AND i.cap_index = c.cap_index
LEFT OUTER JOIN rr.res_table AS t
    ON t.ivoid = r.ivoid
    AND (t.table_type IS NULL OR t.table_type <> 'output')
    AND LOWER(t.table_name) <> 'ivoa.obscore'
LEFT OUTER JOIN rr.capability AS ac
    ON ac.ivoid = r.ivoid
    AND 1 = ivo_nocasematch(ac.standard_id, 'ivo://ivoa.net/std/tap#aux')
LEFT OUTER JOIN rr.interface AS ai
    ON ai.ivoid = ac.ivoid AND ai.cap_index = ac.cap_index AND ai.intf_role = 'std'
WHERE 1 = ivo_nocasematch(c.standard_id, 'ivo://ivoa.net/std/ssa%')
    AND i.intf_role = 'std'
    AND r.ivoid NOT LIKE '%vizier%'
"""

# TAP services that declare productTypeServed = timeseries.
QUERY_TAP_TIMESERIES = """
SELECT DISTINCT r.ivoid, r.res_title, t.table_name, i.access_url
FROM rr.resource AS r
JOIN rr.res_detail AS d ON d.ivoid = r.ivoid
JOIN rr.capability AS c ON c.ivoid = r.ivoid
JOIN rr.interface AS i ON i.ivoid = c.ivoid AND i.cap_index = c.cap_index
LEFT JOIN rr.res_table AS t ON t.ivoid = r.ivoid
WHERE d.detail_xpath = '/productTypeServed'
    AND 1 = ivo_nocasematch(d.detail_value, 'timeseries')
    AND (d.cap_index IS NULL OR d.cap_index = c.cap_index)
    AND 1 = ivo_nocasematch(c.standard_id, 'ivo://ivoa.net/std/tap%')
    AND i.intf_role = 'std'
    AND r.ivoid NOT LIKE '%vizier%'
"""

# Ivoids of the two candidate families above (for coverage dumps).
_CANDIDATE_IVOIDS = """
SELECT r.ivoid
FROM rr.resource AS r
JOIN rr.capability AS c ON c.ivoid = r.ivoid
JOIN rr.interface AS i ON i.ivoid = c.ivoid AND i.cap_index = c.cap_index
WHERE 1 = ivo_nocasematch(c.standard_id, 'ivo://ivoa.net/std/ssa%')
    AND i.intf_role = 'std'
    AND r.ivoid NOT LIKE '%vizier%'
UNION
SELECT r.ivoid
FROM rr.resource AS r
JOIN rr.res_detail AS d ON d.ivoid = r.ivoid
JOIN rr.capability AS c ON c.ivoid = r.ivoid
JOIN rr.interface AS i ON i.ivoid = c.ivoid AND i.cap_index = c.cap_index
WHERE d.detail_xpath = '/productTypeServed'
    AND 1 = ivo_nocasematch(d.detail_value, 'timeseries')
    AND (d.cap_index IS NULL OR d.cap_index = c.cap_index)
    AND 1 = ivo_nocasematch(c.standard_id, 'ivo://ivoa.net/std/tap%')
    AND i.intf_role = 'std'
    AND r.ivoid NOT LIKE '%vizier%'
"""

# No DISTINCT: s.coverage is SMOC; DISTINCT has no equality operator for that type.
QUERY_COVERAGE_SPATIAL = f"""
SELECT s.ivoid, s.coverage, s.ref_system_name
FROM rr.stc_spatial AS s
WHERE s.ivoid IN ({_CANDIDATE_IVOIDS})
"""

QUERY_COVERAGE_TEMPORAL = f"""
SELECT DISTINCT m.ivoid, m.time_start, m.time_end
FROM rr.stc_temporal AS m
WHERE m.ivoid IN ({_CANDIDATE_IVOIDS})
"""

QUERY_COVERAGE_SPECTRAL = f"""
SELECT DISTINCT p.ivoid, p.spectral_start, p.spectral_end
FROM rr.stc_spectral AS p
WHERE p.ivoid IN ({_CANDIDATE_IVOIDS})
"""

_service = None


def _reg():
    global _service
    if _service is None:
        _service = vo.dal.TAPService(REGISTRY_TAP)
    return _service


def _cell(value):
    if value is None or np.ma.is_masked(value):
        return None
    text = str(value).strip()
    if text in ("", "--", "None"):
        return None
    return text


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _write_log(block):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with ADQL_LOG.open("a", encoding="utf-8") as handle:
        handle.write(block)
        if not block.endswith("\n"):
            handle.write("\n")
    print(block, end="" if block.endswith("\n") else "\n")


def run(adql, label, reuse=True):
    """Run one ADQL text on the registry. Log it. Save a VOTable. Return a Table.

    If reuse is true and the VOTable already exists for the same ADQL text,
    that file is read and TAP is not contacted.
    """
    text = adql.strip()
    saved = LOG_DIR / f"{label}.xml"
    saved_adql = LOG_DIR / f"{label}.adql"
    same_adql = (saved_adql.exists()
                 and saved_adql.read_text(encoding="utf-8").strip() == text)
    if reuse and saved.exists() and same_adql:
        table = Table.read(saved)
        _write_log(
            f"\n---- {_stamp()}  LOCAL  {saved}\n"
            f"label: {label}  (not sent to TAP; file already exists)\n"
            f"ADQL that produced this file:\n{text}\n"
            f"---- reused: {len(table)} rows\n"
        )
        return table
    _write_log(
        f"\n---- {_stamp()}  TAP  {REGISTRY_TAP}\n"
        f"label: {label}\n"
        f"ADQL:\n{text}\n"
    )
    try:
        table = _reg().run_sync(text).to_table()
    except Exception as exc:
        _write_log(f"---- error: {exc}\n")
        raise
    table.write(saved, format="votable", overwrite=True)
    saved_adql.write_text(text + "\n", encoding="utf-8")
    _write_log(f"---- result: {len(table)} rows  saved: {saved}\n")
    return table


# Keyword fields for SSA records (T-003): (label, table alias + FROM part, column).
# Each FROM part is joined to the SSA ivoid set below. rr.table_column waits.
KEYWORD_FIELDS = [
    ("res_title", "rr.resource AS x", "x.res_title"),
    ("res_description", "rr.resource AS x", "x.res_description"),
    ("short_name", "rr.resource AS x", "x.short_name"),
    ("res_subject", "rr.res_subject AS x", "x.res_subject"),
    ("cap_description", "rr.capability AS x", "x.cap_description"),
    ("table_name", "rr.res_table AS x", "x.table_name"),
    ("table_title", "rr.res_table AS x", "x.table_title"),
    ("table_description", "rr.res_table AS x", "x.table_description"),
    ("schema_name", "rr.res_schema AS x", "x.schema_name"),
    ("schema_title", "rr.res_schema AS x", "x.schema_title"),
    ("schema_description", "rr.res_schema AS x", "x.schema_description"),
]

_SSA_IVOIDS = """SELECT c.ivoid FROM rr.capability AS c
        WHERE 1 = ivo_nocasematch(c.standard_id, 'ivo://ivoa.net/std/ssa%')
            AND c.ivoid NOT LIKE '%vizier%'"""


def keyword_query(patterns):
    """One ADQL query: every keyword-field value of an SSA ivoid matching any pattern.

    Result columns: ivoid, hit_field (which registry column), hit_text (its text).
    """
    match = " OR ".join(f"{{col}} ILIKE '{p}'" for p in patterns)
    branches = []
    for label, source, column in KEYWORD_FIELDS:
        branches.append(
            f"SELECT DISTINCT x.ivoid, '{label}' AS hit_field, {column} AS hit_text\n"
            f"FROM {source}\n"
            f"WHERE x.ivoid IN ({_SSA_IVOIDS})\n"
            f"    AND ({match.format(col=column)})"
        )
    return "\nUNION ALL\n".join(branches)


# Tier 3 (T-012): TAP services found by keywords only.
# Candidate TAP ivoids: have a TAP capability (std/tap, also tap#aux of per-table
# records), are NOT VizieR, NOT SSA records (tier 2), and have no
# /productTypeServed at all. If that detail exists: timeseries is already
# tier 1; any other value means "not timeseries" and we skip the record.
_TAP_ONLY_IVOIDS = """SELECT c.ivoid FROM rr.capability AS c
        WHERE 1 = ivo_nocasematch(c.standard_id, 'ivo://ivoa.net/std/tap%')
            AND c.ivoid NOT LIKE '%vizier%'
            AND c.ivoid NOT IN (
                SELECT s.ivoid FROM rr.capability AS s
                WHERE 1 = ivo_nocasematch(s.standard_id, 'ivo://ivoa.net/std/ssa%'))
            AND c.ivoid NOT IN (
                SELECT d.ivoid FROM rr.res_detail AS d
                WHERE d.detail_xpath = '/productTypeServed')"""

# Fields whose hit belongs to one table (only that table becomes a candidate).
# Hits in all other fields are resource-level: every table of the record is a candidate.
_TABLE_LEVEL_FIELDS = {"table_name", "table_title", "table_description"}


def tap_keyword_query(patterns):
    """One ADQL query: TAP routes (url + table) whose registry text matches a pattern.

    POSITIVE HITS ONLY. A TAP service without a hit is not listed, so lightcurve
    resources whose registry text lacks our words are MISSED (not "unknown").

    Result: one row per (ivoid, TAP url, table, hit): ivoid, res_title, access_url,
    table_name, hit_table, hit_field, hit_text. Resource-level hits give every
    data table of the record (not 'output', not ivoa.obscore); table-level hits
    give only the matching table. A record with no table listed has table_name NULL.
    """
    match = " OR ".join(f"{{col}} ILIKE '{p}'" for p in patterns)
    branches = []
    for label, source, column in KEYWORD_FIELDS:
        hit_table = "x.table_name" if label in _TABLE_LEVEL_FIELDS else "''"
        branches.append(
            f"SELECT DISTINCT x.ivoid, '{label}' AS hit_field, {column} AS hit_text,"
            f" {hit_table} AS hit_table\n"
            f"FROM {source}\n"
            f"WHERE x.ivoid IN ({_TAP_ONLY_IVOIDS})\n"
            f"    AND ({match.format(col=column)})"
        )
    hits = "\nUNION ALL\n".join(branches)
    return f"""SELECT DISTINCT h.ivoid, r.res_title, i.access_url, t.table_name,
       h.hit_table, h.hit_field, h.hit_text
FROM (
{hits}
) AS h
JOIN rr.resource AS r ON r.ivoid = h.ivoid
JOIN rr.capability AS c ON c.ivoid = h.ivoid
    AND 1 = ivo_nocasematch(c.standard_id, 'ivo://ivoa.net/std/tap%')
JOIN rr.interface AS i ON i.ivoid = c.ivoid AND i.cap_index = c.cap_index
    AND i.intf_role = 'std'
LEFT OUTER JOIN rr.res_table AS t ON t.ivoid = h.ivoid
    AND (t.table_type IS NULL OR t.table_type <> 'output')
    AND LOWER(t.table_name) <> 'ivoa.obscore'
    AND (h.hit_table = '' OR h.hit_table = t.table_name)"""


def collect(table, kind):
    """Group an already-fetched candidate table by access URL.

    {url: {"kind", "ivoids": {ivoid: title}, "tables": set}}
    """
    routes = {}
    has_table = "table_name" in table.colnames
    for row in table:
        url = _cell(row["access_url"])
        ivoid = _cell(row["ivoid"])
        if not url or not ivoid:
            continue
        route = routes.setdefault(url, {"kind": kind, "ivoids": {}, "tables": set()})
        route["ivoids"][ivoid] = _cell(row["res_title"]) or ""
        if has_table:
            name = _cell(row["table_name"])
            if name:
                route["tables"].add(name)
    return routes


def coverage_by_ivoid(spatial, temporal, spectral):
    """ivoid -> list of declared intervals/MOCs. Missing key means unknown."""

    def gather(table, columns):
        by_id = {}
        for row in table:
            ivoid = _cell(row["ivoid"])
            if not ivoid:
                continue
            by_id.setdefault(ivoid, []).append(tuple(_cell(row[c]) for c in columns))
        return by_id

    return {
        "spatial": gather(spatial, ("coverage", "ref_system_name")),
        "temporal": gather(temporal, ("time_start", "time_end")),
        "spectral": gather(spectral, ("spectral_start", "spectral_end")),
    }
