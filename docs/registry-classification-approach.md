# Registry classification: approach (SSA and TAP)

Registry TAP: `http://reg.g-vo.org/tap`. Copy any ADQL below into TOPCAT against that service.

Goal: build a **local index of lightcurve routes**. A route is an endpoint (access URL) plus, for TAP, a table. The ivoid is a label on that route, not the unit of discovery. VizieR is excluded everywhere (`ivoid NOT LIKE '%vizier%'`).

SSA and TAP are treated differently because SSA serves **both** lightcurves and spectra from the same protocol, while TAP can declare `productTypeServed = timeseries` (trusted) or not (then we only have words in the registry).

---

## 1. SSA resources: list, then classify

**Why.** SSAP is the main VO protocol for 1-D products. Many records are spectra. We need every SSA endpoint first, then split lightcurves from spectra using registry text. Better to keep extra spectra than to drop a lightcurve.

### Step 1 — list all SSA routes

Join resource, SSA capability, and its `std` interface. Attach the record’s data tables (not `output`, not `ivoa.obscore`) and its auxiliary TAP URL (`tap#aux`), if any. Records with no table or no aux TAP stay in the result (`LEFT OUTER JOIN`).

```sql
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
```

**Result:** 210 rows (`/home/voz/projects/UPJS/DataDiscovery/VO_lc_discovery/discovery/logs/ssa_candidates.xml`). About 209 SSA URLs; a few records have two tables.

`ivoa.obscore` is dropped for now: it is a shared table. A later route would need a stored filter on `dataproduct_type` / `dataproduct_subtype`, not on `obs_collection`.

### Step 2 — keyword hits on those SSA ivoids

SSA has no `productTypeServed` we can trust for “lightcurve vs spectrum”. We search the registry fields of **SSA ivoids only** with `ILIKE`.

Positive (keep): `%time%series%`, `%light%curve%`  
Stop (spectra): `%spectra%`, `%spectrum%`, `%spectroscopic%`, `%spectrophotometer%` (and later `%kurucz%`)

Fields (same list for TAP keywords later). `rr.table_column` is **not** searched.

| Table | Columns |
|---|---|
| `rr.resource` | `res_title`, `res_description`, `short_name` |
| `rr.res_subject` | `res_subject` |
| `rr.capability` | `cap_description` |
| `rr.res_table` | `table_name`, `table_title`, `table_description` |
| `rr.res_schema` | `schema_name`, `schema_title`, `schema_description` |

Shape of the query (one `UNION ALL` branch per field):

```sql
SELECT DISTINCT x.ivoid, 'res_title' AS hit_field, x.res_title AS hit_text
FROM rr.resource AS x
WHERE x.ivoid IN (
        SELECT c.ivoid FROM rr.capability AS c
        WHERE 1 = ivo_nocasematch(c.standard_id, 'ivo://ivoa.net/std/ssa%')
            AND c.ivoid NOT LIKE '%vizier%')
    AND (x.res_title ILIKE '%time%series%'
      OR x.res_title ILIKE '%light%curve%'
      OR x.res_title ILIKE '%spectra%'
      OR x.res_title ILIKE '%spectrum%'
      OR x.res_title ILIKE '%spectroscopic%'
      OR x.res_title ILIKE '%spectrophotometer%')
UNION ALL
-- same for res_description, short_name, res_subject, cap_description,
-- table_name, table_title, table_description,
-- schema_name, schema_title, schema_description
```

**Result:** 418 rows (`/home/voz/projects/UPJS/DataDiscovery/VO_lc_discovery/discovery/logs/ssa_keyword_hits.xml`): only the fields that matched, with the matching text.

### Step 3 — classify locally (not in ADQL)

For each SSA ivoid:

- any **positive** hit → `lightcurve` (positive **always** wins, even if stop words also match);
- else any **stop** hit → `spectra`;
- else → `undecided` (kept in the table; **not** put in the index).

**Result:** `/home/voz/projects/UPJS/DataDiscovery/VO_lc_discovery/discovery/logs/ssa_classified.xml`

| Verdict | Rows | ivoids | Notes |
|---|---|---|---|
| lightcurve | 13 | 13 | 11 have an auxiliary TAP URL |
| spectra | 137 | 136 | |
| undecided | 60 | 60 | mostly spectra whose text never said “spectra/spectrum” |

This split is usable: the 13 lightcurve ivoids are the known photometric SSA services (UPJS, BGDS, Gaia DR2 LC, OMC, …). Weak cases (e.g. CARMENES Spectra, kept because a table description said “time series”) are accepted on purpose.

---

## 2. TAP resources: two lists, two meanings

TAP is not one protocol-for-products the way SSA is. A TAP URL often serves a whole archive. We therefore **do not** keyword-tag the declared timeseries TAP records, and we tried a **separate** keyword search for everything else.

### 2a. Declared TAP timeseries (no keyword classification)

**Why.** `rr.res_detail` `/productTypeServed` = `timeseries` is the registry’s own statement. Trust it; do not run keywords on these records.

```sql
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
```

**Result:** 19 rows, **2 TAP URLs** (`/home/voz/projects/UPJS/DataDiscovery/VO_lc_discovery/discovery/logs/tap_timeseries.xml`): `http://dc.g-vo.org/tap` and `https://skvo.science.upjs.sk/tap`, each shared by several ivoids (ObsCore plus per-collection records). This list is **not** classified by words.

### 2b. Other TAP services, by keywords only (tier 3)

**Why.** Most TAP services never set `productTypeServed`. Some still hold lightcurves. We look for the **same positive words** in the same registry fields, on TAP ivoids that have **no** `/productTypeServed` (see below) and are **not** SSA records (their `tap#aux` is already on the SSA list). Stop words are **not** used. **Positive hits only:** a TAP resource with no matching word is omitted, so real lightcurve resources can be missed.

Ivoids considered. Any record that **has** `/productTypeServed` is out of this search: if the value is `timeseries` we already have it (2a); if it is anything else the provider declared it is not timeseries. Keywords apply only when that detail is **absent**.

```sql
SELECT c.ivoid FROM rr.capability AS c
WHERE 1 = ivo_nocasematch(c.standard_id, 'ivo://ivoa.net/std/tap%')
    AND c.ivoid NOT LIKE '%vizier%'
    AND c.ivoid NOT IN (
        SELECT s.ivoid FROM rr.capability AS s
        WHERE 1 = ivo_nocasematch(s.standard_id, 'ivo://ivoa.net/std/ssa%'))
    AND c.ivoid NOT IN (
        SELECT d.ivoid FROM rr.res_detail AS d
        WHERE d.detail_xpath = '/productTypeServed')
```

Hits: `UNION ALL` over the same eleven fields, `ILIKE '%time%series%' OR ILIKE '%light%curve%'` only.

Then join each hit to the TAP URL and to tables:

- **Table-level** hit (`table_name` / `table_title` / `table_description`) → only that table.
- **Resource-level** hit (title, description, subject, schema, capability) → **every** data table of that record.

```sql
SELECT DISTINCT h.ivoid, r.res_title, i.access_url, t.table_name,
       h.hit_table, h.hit_field, h.hit_text
FROM ( /* UNION ALL of the eleven field queries, TAP-only ivoids, positive ILIKE */ ) AS h
JOIN rr.resource AS r ON r.ivoid = h.ivoid
JOIN rr.capability AS c ON c.ivoid = h.ivoid
    AND 1 = ivo_nocasematch(c.standard_id, 'ivo://ivoa.net/std/tap%')
JOIN rr.interface AS i ON i.ivoid = c.ivoid AND i.cap_index = c.cap_index
    AND i.intf_role = 'std'
LEFT OUTER JOIN rr.res_table AS t ON t.ivoid = h.ivoid
    AND (t.table_type IS NULL OR t.table_type <> 'output')
    AND LOWER(t.table_name) <> 'ivoa.obscore'
    AND (h.hit_table = '' OR h.hit_table = t.table_name)
```

**Result:** 3 926 raw hit rows (`/home/voz/projects/UPJS/DataDiscovery/VO_lc_discovery/discovery/logs/tap_keyword_hits.xml`); after grouping, **500** (ivoid, URL, table) rows, 110 ivoids, **24 TAP URLs** (`/home/voz/projects/UPJS/DataDiscovery/VO_lc_discovery/discovery/logs/tap_keyword_classified.xml`).

**Why this result is not usable as an index.** Most hits are resource-level (`schema_description`, `schema_title`, `res_description`). One matching sentence on a big TAP service then marks **all** of its tables as lightcurve candidates. Example: `http://dc.g-vo.org/tap` → 272 tables. That is the opposite of SSA, where the service *is* the product. TAP’s unit is the table, and a schema/resource hit is too coarse.

What *did* work in that table are the **table-level** hits (e.g. `applause_dr3.lightcurve`). Those are the part worth keeping if this tier is redesigned: search table name/title/description (and later columns), do **not** expand a resource- or schema-level hit to every table.
