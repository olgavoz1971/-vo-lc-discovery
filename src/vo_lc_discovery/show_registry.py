"""Dump index candidates for manual checking.

    python -m vo_lc_discovery.show_registry

Prints ADQL and URLs. Full tables and the ADQL log are under discovery/logs/.
"""
from . import registry as rg


def _cov_note(ivoid, by_ivoid):
    spa = by_ivoid["spatial"].get(ivoid)
    tem = by_ivoid["temporal"].get(ivoid)
    spe = by_ivoid["spectral"].get(ivoid)
    parts = [
        f"spa={'unknown' if spa is None else str(len(spa)) + ' moc'}",
        f"tem={'unknown' if tem is None else str(len(tem)) + ' int'}",
        f"spe={'unknown' if spe is None else str(len(spe)) + ' int'}",
    ]
    if tem:
        parts.append("time=" + ";".join(f"{a}..{b}" for a, b in tem))
    if spe:
        parts.append("spec=" + ";".join(f"{a}..{b}" for a, b in spe))
    return "  ".join(parts)


def show_routes(title, routes, by_ivoid):
    shared = sum(len(r["ivoids"]) > 1 for r in routes.values())
    print("=" * 78)
    print(title)
    print(f"{len(routes)} URLs, {shared} shared by several ivoids")
    print("spa/tem/spe: declared row counts, or unknown (no registry coverage row)")
    print()
    for url, route in sorted(routes.items()):
        print(url)
        for ivoid, name in route["ivoids"].items():
            print(f"    {ivoid}  |  {name}")
            print(f"        {_cov_note(ivoid, by_ivoid)}")
        if route["tables"]:
            print("    tables:", ", ".join(sorted(route["tables"])))


def main():
    rg._write_log(f"\n======== session {rg._stamp()}  show_registry ========\n")
    ssa = rg.run(rg.QUERY_SSA, "ssa_candidates")
    tap = rg.run(rg.QUERY_TAP_TIMESERIES, "tap_timeseries")
    spatial = rg.run(rg.QUERY_COVERAGE_SPATIAL, "coverage_spatial")
    temporal = rg.run(rg.QUERY_COVERAGE_TEMPORAL, "coverage_temporal")
    spectral = rg.run(rg.QUERY_COVERAGE_SPECTRAL, "coverage_spectral")
    by_ivoid = rg.coverage_by_ivoid(spatial, temporal, spectral)
    show_routes("SSA services (not yet split from spectra)", rg.collect(ssa, "ssa"), by_ivoid)
    show_routes("TAP, productTypeServed = timeseries", rg.collect(tap, "tap"), by_ivoid)
    print("=" * 78)
    print("ADQL log:", rg.ADQL_LOG)
    print("VOTables:", rg.LOG_DIR)


if __name__ == "__main__":
    main()
