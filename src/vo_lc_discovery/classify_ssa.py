"""T-003: split SSA candidates into lightcurve / spectra / undecided by keywords.

    python -m vo_lc_discovery.classify_ssa

One TAP query (keyword hits). SSA candidates come from ssa_candidates.xml
(T-002), reused, not re-queried. A positive hit wins over a stop hit.
Writes discovery/logs/ssa_classified.xml for TOPCAT.
"""
import json
import re
from pathlib import Path

from astropy.table import Table

from . import registry as rg

KEYWORDS = Path(__file__).with_name("keywords.json")


def _ilike(pattern):
    """ADQL ILIKE pattern -> compiled regex (only % and _ are special)."""
    body = "".join(".*" if ch == "%" else "." if ch == "_" else re.escape(ch)
                   for ch in pattern)
    return re.compile(f"^{body}$", re.IGNORECASE | re.DOTALL)


def classify(candidates, hits, positive, stop):
    pos_re = [(p, _ilike(p)) for p in positive]
    stop_re = [(p, _ilike(p)) for p in stop]

    found = {}
    for row in hits:
        ivoid, field, value = (rg._cell(row[c]) for c in ("ivoid", "hit_field", "hit_text"))
        if not ivoid or not value:
            continue
        entry = found.setdefault(ivoid, {"positive": set(), "stop": set()})
        for p, rx in pos_re:
            if rx.match(value):
                entry["positive"].add(f"{field}:{p}")
        for p, rx in stop_re:
            if rx.match(value):
                entry["stop"].add(f"{field}:{p}")

    # One output row per (ivoid, SSA url, table); auxiliary TAP urls joined by ';'.
    grouped = {}
    for row in candidates:
        ivoid = rg._cell(row["ivoid"])
        key = (ivoid, rg._cell(row["access_url"]), rg._cell(row["table_name"]) or "")
        item = grouped.setdefault(key, {"title": rg._cell(row["res_title"]) or "",
                                        "aux": []})
        aux = rg._cell(row["aux_tap_url"])
        if aux and aux not in item["aux"]:
            item["aux"].append(aux)

    rows = []
    for (ivoid, url, table_name), item in grouped.items():
        entry = found.get(ivoid, {"positive": set(), "stop": set()})
        if entry["positive"]:
            verdict = "lightcurve"
        elif entry["stop"]:
            verdict = "spectra"
        else:
            verdict = "undecided"
        rows.append((ivoid, url, table_name, ";".join(item["aux"]), item["title"],
                     verdict, " ".join(sorted(entry["positive"])),
                     " ".join(sorted(entry["stop"]))))
    return Table(rows=rows, names=("ivoid", "access_url", "table_name", "aux_tap_url",
                                   "res_title", "verdict", "positive_hits", "stop_hits"))


def main():
    words = json.loads(KEYWORDS.read_text(encoding="utf-8"))
    rg._write_log(f"\n======== session {rg._stamp()}  classify_ssa ========\n"
                  f"keywords: {KEYWORDS}\n"
                  f"positive: {words['positive']}  stop: {words['stop']}\n")
    candidates = rg.run(rg.QUERY_SSA, "ssa_candidates")
    hits = rg.run(rg.keyword_query(words["positive"] + words["stop"]), "ssa_keyword_hits")
    result = classify(candidates, hits, words["positive"], words["stop"])

    out = rg.LOG_DIR / "ssa_classified.xml"
    result.write(out, format="votable", overwrite=True)
    counts = {v: int((result["verdict"] == v).sum())
              for v in ("lightcurve", "spectra", "undecided")}
    rg._write_log(f"---- LOCAL  written: {out}  ({len(result)} rows)  {counts}\n")

    for verdict in ("lightcurve", "undecided"):
        print("=" * 78)
        print(verdict, counts[verdict])
        for row in result[result["verdict"] == verdict]:
            print(row["access_url"])
            print(f"    {row['ivoid']}  |  {row['res_title']}")
            if row["table_name"] or row["aux_tap_url"]:
                print(f"    table: {row['table_name'] or '-'}   aux TAP: {row['aux_tap_url'] or '-'}")
            if row["positive_hits"]:
                print(f"    + {row['positive_hits']}")
            if row["stop_hits"]:
                print(f"    - {row['stop_hits']}")
    print("=" * 78)
    print(f"spectra {counts['spectra']}  (listed in {out})")


if __name__ == "__main__":
    main()
