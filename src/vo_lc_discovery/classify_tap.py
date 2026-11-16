"""T-012, tier 3: TAP-served lightcurve candidates found by keywords only.

    python -m vo_lc_discovery.classify_tap

WARNING, POSITIVE HITS ONLY: a TAP resource is listed only if its registry
text matches a positive word (keywords.json "positive"; stop words are NOT
used here). TAP resources without such words are not listed, so real
lightcurve resources can be MISSED. Absence from the result means "no hit",
not "not lightcurves".

Not searched here: VizieR; SSA records (tier 2, including their tap#aux);
any ivoid that has /productTypeServed (timeseries is already tier 1; any
other value means the provider declared it is not timeseries).
Dropped for now: ivoa.obscore, tables of type 'output', rr.table_column.

One registry query. Output: discovery/logs/tap_keyword_classified.xml
"""
import json

from astropy.table import Table

from . import registry as rg
from .classify_ssa import KEYWORDS, _ilike


def classify(hits, positive):
    """Group hit rows by (ivoid, TAP url, table); keep the matched field:pattern."""
    pos_re = [(p, _ilike(p)) for p in positive]
    grouped = {}
    for row in hits:
        ivoid = rg._cell(row["ivoid"])
        url = rg._cell(row["access_url"])
        table = rg._cell(row["table_name"]) or ""
        hit_table = rg._cell(row["hit_table"]) or ""
        text = rg._cell(row["hit_text"])
        if not ivoid or not url or not text:
            continue
        if hit_table and not table:     # table-level hit on a dropped table (obscore)
            continue
        item = grouped.setdefault((ivoid, url, table),
                                  {"title": rg._cell(row["res_title"]) or "",
                                   "hits": set()})
        field = rg._cell(row["hit_field"])
        for p, rx in pos_re:
            if rx.match(text):
                item["hits"].add(f"{field}:{p}")
    rows = [(ivoid, url, table, item["title"], " ".join(sorted(item["hits"])))
            for (ivoid, url, table), item in sorted(grouped.items())]
    return Table(rows=rows, names=("ivoid", "access_url", "table_name",
                                   "res_title", "positive_hits"),
                 dtype=("U300", "U500", "U200", "U500", "U1000"))


def main():
    words = json.loads(KEYWORDS.read_text(encoding="utf-8"))
    positive = words["positive"]
    rg._write_log(f"\n======== session {rg._stamp()}  classify_tap (tier 3) ========\n"
                  f"keywords: {KEYWORDS}\n"
                  f"positive only: {positive}  (stop words not used for TAP)\n")
    hits = rg.run(rg.tap_keyword_query(positive), "tap_keyword_hits")
    result = classify(hits, positive)

    out = rg.LOG_DIR / "tap_keyword_classified.xml"
    result.write(out, format="votable", overwrite=True)
    ivoids = len(set(result["ivoid"]))
    rg._write_log(f"---- LOCAL  written: {out}  ({len(result)} rows, {ivoids} ivoids)\n")

    print("=" * 78)
    print("TAP, positive keyword hits only (resources without hits are NOT listed)")
    print(f"{len(result)} rows, {ivoids} ivoids")
    for row in result:
        print(row["access_url"])
        print(f"    {row['ivoid']}  |  {row['res_title']}")
        print(f"    table: {row['table_name'] or '-'}")
        print(f"    + {row['positive_hits']}")


if __name__ == "__main__":
    main()
