# vo-lc-discovery: design draft

Package: `vo-lc-discovery` (import name `vo_lc_discovery`). Status: draft 0.2, after the spike phase and the first round of package decisions. Items marked **(verify)** are not confirmed against a standard or a live service.

## 1. Goal and use case

A user (a person, a web application or an AI agent) gives a sky region, a time interval and a rough spectral position. The package returns:

- **(a)** a list of *routes* (providers' endpoints) that probably hold lightcurves matching the request, each with a flag saying how sure we are;
- **(b)** on request for one chosen route, the provider's own response for that request.

## 2. Rules

1. Respect the registry and the providers: no heavy or repeated load where it can be avoided.
2. Respect the user's time: the expensive work happens once, offline.
3. Return fair results: every result carries a flag saying how certain it is, and what was not checked.
4. The spectral position is deliberately rough: one number, not a range.
5. The time interval is rough as well: no time scale is stated or converted.

## 3. Scope

**In scope**

- Building and using a local index of lightcurve routes.
- One live registry query per user request: the `productTypeServed = timeseries` query, which is cheap.
- Providers served by SSAP, and TAP-served tables (ObsCore and keyword-based discovery).
- Step (b): returning what the provider serves, in the provider's own shape.

**Out of scope for now**

- Other user-triggered registry queries (the "fresh and complete" mode). Postponed.
- Extracting the lightcurve itself: datalink and SODA handling, array columns, per-point rows.
- A common row structure for results. None will be invented.
- Keyword search design (planned, a later step).
- VizieR is excluded from the index.

## 4. Vocabulary

| Term | Meaning |
|---|---|
| Resource / record | A registry record, identified by an `ivoid`. It describes something; it is not the data. |
| Capability | A function a record offers, identified by its `standard_id` (SSA, TAP, datalink, ...). |
| Interface | A concrete way to call a capability; carries the access URL. |
| Route | The unit of discovery: an endpoint plus, for TAP, a table (and a filter for shared tables such as `ivoa.obscore`). |
| Auxiliary capability | A capability with an `#aux` suffix saying "the data of this record is also reachable here". |
| Reason | Why a route has its flag, e.g. "subject keyword: light curves". |

The route, not the ivoid, is the unit. One ivoid can have several URLs, and several ivoids can share one URL.

## 5. Principles for the two kinds of code

- **Registry side.** The searchable GAVO registry is the main registry. Its extensions (`rr.stc_*` tables, `ivo_*` and `gavo_*` UDFs) may be used there, but they are isolated in one module so that other registries can be supported later.
- **Provider side.** Standards only (TAP, SSAP, ObsCore, TAP_SCHEMA, datalink). Nothing may assume a particular server, and DaCHS in particular.
- **No assumption about the database behind any service**, neither the registry's nor a provider's.

## 6. Architecture

### 6.1 Offline: build and keep the index

1. **Collect candidate routes** from the registry.
2. **Classify** each route by content.
3. **Store coverage** (space, time, spectral) as the registry declares it.
4. **Store query hints**, so that a user request needs no metadata lookup.
5. **Refresh** from time to time, using the record update dates to re-examine only what changed.

### 6.2 Per user request

1. Run the live `productTypeServed` query, carrying the space, time and spectral conditions.
2. Filter the index by coverage.
3. Merge both by route. The live answer overrides a stored flag for that request.
4. Return the list with flags and with a statement of what was not checked.

### 6.3 Step (b), per chosen route

Send the user's constraints to the route in the form it understands, and return the provider's response unchanged, with a note on which constraints could not be applied.

## 7. Candidate sources

### 7.1 SSA family

- Registry query: SSA capability (`ivo://ivoa.net/std/ssa%`, case-insensitive), interface role `std`.
- Result sizes seen in the spike: 209 service rows, 95 table rows (the repeated ivoids come from SSA plus ObsCore table pairs).
- Many services list no tableset, so the registry says nothing about their content.
- Tables of type `output` are excluded (`table_type != 'output' OR table_type IS NULL`).

### 7.2 TAP family

- Declared: `rr.res_detail` with `detail_xpath = '/productTypeServed'` and value `timeseries`.
- ObsCore: rows of `ivoa.obscore` with `dataproduct_type = 'timeseries'`.
- Keywords: words in title, description, subject, table names, column descriptions and UCDs (see 8.2).

Tables shared across collections (`ivoa.obscore`) need a stored filter. The filter uses `dataproduct_type` and `dataproduct_subtype` (e.g. `dataproduct_type = 'timeseries'`), not `obs_collection`.

## 8. Classification

Two independent labels per route.

### 8.1 Content flag

`certain` / `highly_likely` / `probable` / `unlikely`.

- The flag reflects the strength of the reasons. It is not a calibrated probability.
- Each flag stores its **reasons** and the **rule version**, so that results can explain themselves and old flags can be invalidated.

### 8.2 Reasons, in order of trust

1. Declared `productTypeServed`.
2. Controlled terms: UAT concepts (`rr.subject_uat`, GAVO UDF `gavo_vocmatch`) and `res_subject`.
3. Column UCDs from `rr.table_column`, where providers published them (count the rows first).
4. Table names and descriptions.
5. Words in resource title and description.
6. Verification against the provider (planned; the design has not been discussed): is it really lightcurves, not spectra?

Example reason codes: `declared_timeseries`, `subject_keyword`, `column_ucd`, `table_name`, `description_words`, `checked_response`.

### 8.3 Fit per axis

For each of space, time and spectral position: `covers`, `outside` or `unknown`.

- Any `outside` excludes the route (dropped from the default result; a switch can include them).
- Any `unknown` downgrades the route to "worth checking".
- Registry coverage is coarse, so `covers` means "may have data", not "has data".

## 9. Input parameters

| Parameter | Content |
|---|---|
| `region` | Starts as a cone: RA, Dec (ICRS, degrees), radius (degrees), optional name as the user gave it. A MOC may be accepted later. Public calls take `region`, so that nothing else depends on its type. |
| `time` | A start and an end in MJD. No time scale: the precision is rough, and ISO strings or astropy `Time` inputs are converted to MJD with the scale difference ignored. |
| `specmid` | One number, the rough spectral position (an effective wavelength), as an astropy `Quantity` or a number with the unit stated. No default unit. |

- The name `specmid` follows SSA's `ssa_specmid`. **(verify)** the exact definition and units in the SSA text.
- **Filter helpers** convert known filters (V, R, ...) and coarse names ("optical", "radio") into a representative `specmid`. The helpers are a convenience and are not part of the core model.
- Test against the registry: `rr.stc_spectral` holds energy values in Joules, according to the GAVO registry coverage paper. **(verify)** The specmid wavelength is converted to energy, and a route fits if the energy lies between `spectral_start` and `spectral_end` of one of its rows.

## 10. Index

A single **SQLite file**, small enough to ship with the package through GitHub (VizieR excluded). No parquet.

### 10.1 Stored models

| Model | Content |
|---|---|
| `Route` | `route_id`, kind (`ssa` or `tap`), access URL, table name (empty for SSA), stored filter for shared tables (`dataproduct_type` / `dataproduct_subtype`), content flag, rule version, query hints, status |
| `Label` | `route_id`, ivoid, title |
| `Reason` | `route_id`, reason code, source (which registry field or check), detail, rule version |

Query hints: an ordered list of candidate position expressions (target position first, then location), the time column if known, and whether a datalink capability exists.

### 10.2 Coverage as the registry has it

| Table | Columns |
|---|---|
| spatial | `route_id`, `coverage` (MOC string), `source`, `retrieved` |
| temporal | `route_id`, `time_start`, `time_end` (MJD), `source`, `retrieved` |
| spectral | `route_id`, `spectral_start`, `spectral_end` (Joules), `source`, `retrieved` |

- Several intervals are several rows, as in the registry.
- **No rows means unknown.** No NULL markers are used.
- `source` and `retrieved` are the only additions. They tell registry-declared values from any computed later, and from stale ones.
- Registry coverage belongs to an ivoid. If several ivoids point to one route, the open point is whether to store the union, which can overstate the coverage.

## 11. Public surface

Five calls exported from the package root, plus nothing else:

| Call | Purpose |
|---|---|
| `discover(region, time, specmid, ...)` | Step (a). Routes with flags, fit per axis, and the list of what was not checked. |
| `describe(route_id)` | Reasons for one route, its labels (ivoids and titles), query hints, last check. |
| `fetch(route_id, region, time, specmid, ...)` | Step (b). The provider's response unchanged, with applied and unapplied constraints. |
| `estimate(route_id, ...)` | Dry run: what `fetch` would send, and a rough cost. |
| `index_info()` | Snapshot date, rule version, counts per flag. |

Per-request models:

| Model | Content |
|---|---|
| `RouteMatch` | Route identifiers, fit per axis (`fit_space`, `fit_time`, `fit_specmid`), whether the match came from the index or from the live query, one overall note derived from the fits |
| `DiscoveryResult` | Query echo, index snapshot info, matches, labels and reasons for those matches, warnings, `not_checked` |
| `Retrieval` | `route_id`, the request as sent (ADQL text or SSAP URL), constraints applied, constraints not applied, timing, provider status, the provider's response untouched |
| `Estimate` | What `fetch` would send, which endpoints it would call, rough cost |
| `IndexInfo` | Snapshot date, rule version, counts |

## 12. Output: VOTable

All results are returned as VOTables and serialised that way.

### 12.1 `DiscoveryResult`

- Query echo and snapshot info as PARAMs on the resource.
- One TABLE of matches, one row per route: `route_id`, `kind`, `access_url`, `table_name`, `flag`, `fit_space`, `fit_time`, `fit_specmid`, `source`. The flag and fit columns carry fixed value lists.
- Separate TABLEs `labels` and `reasons`, linked by `route_id`, so that the matches table stays flat and has no list-valued cells.
- Warnings and `not_checked` as INFO elements.
- Coverage MOCs are not shipped. Only the fit status goes out.

### 12.2 `Retrieval`

A single file: the wrapper carries the PARAMs and INFOs, and the provider's tables are copied in unchanged. For a provider answer in another format, the wrapper holds a conversion note.

## 13. Principles for the public objects

- `route_id` is a stable hash of the normalised endpoint, table and filter, so that equal routes have equal ids on any machine.
- Flag values are fixed strings: `certain`, `highly_likely`, `probable`, `unlikely`.
- No hidden state and no global caches visible to the caller.
- Warnings are part of the result, not log lines.
- Conservative defaults: a result cap, request timeouts, one route per `fetch`.
- No interactive prompts and no printing.
- Docstrings are written as tool descriptions, because agents read them. An MCP server can later be a thin layer over the five calls.

## 14. Project decisions

- **Synchronous**, with timeouts. Calls are free of global state so that async wrappers can be added later.
- **Dependencies:** `pyvo`, `astropy`, `numpy`, `mocpy`. A later package for producing lightcurves may share them.
- **Tests:** recorded registry and provider responses replayed offline, so that tests do not depend on, or load, external services.
- **Registry refresh:** a maintainer tool in the same repository, installed through an extra, with its own command-line entry point. It is never imported by the query path, so users and agents cannot trigger it.

## 15. Registry facts from the spike

- `rr.res_table` is one-to-many, so a joined result has one row per table.
- Tables of type `output` describe a service's response and are not data tables.
- DaCHS publishes per-table records with an aux TAP capability and a relationship to the service. This is the mechanism of the IVOA note on discovering data collections within services.
- A DaCHS-style record exposes many capabilities: SSA, `tap#aux`, datalink, SODA and VOSI (`capabilities`, `availability`, `tables`). Only SSA, TAP and datalink matter for discovery.
- Two distinct ivoids can share one SSAP URL without a relationship between them. One ivoid can have two URLs.
- SSA position columns: `ssa_targetpos` has UCD `pos.eq;src` (the target); `ssa_location` has `pos.eq` (the aperture centre). For "is there a lightcurve of this star" prefer the target position and fall back to the location. Both can be empty, so all candidates are tried.
- ObsCore has `s_ra` and `s_dec` as separate columns (`pos.eq.ra`, `pos.eq.dec`) and `s_fov` as the diameter. **(verify)** against the ObsCore text.
- `ref_system_name` in `rr.stc_spatial` is NULL for ICRS. Check the values that occur before relying on this.
- Registry coverage is sparse, especially in time. Whether a resource without coverage has no row or a row with NULLs must be checked with count queries.
- Standard IDs differ in case (`.../std/TAP` and `.../std/tap`): compare case-insensitively.

## 16. Row shapes at step (b)

Provider responses differ. Three shapes are known:

- **Dataset row**: one row describes a lightcurve and points to the data (access reference or datalink).
- **Array row**: one row holds a whole lightcurve in array columns.
- **Measurement row**: one row is one point, and a lightcurve is a group of rows.

Decision: no mapping to a common structure. The provider's response is returned. A shape label is **undecided**, and the provider responses will be surveyed first.

## 17. Open questions

- Shape labels (section 16).
- Policy for mixed endpoints (spectra and lightcurves in one table) and for aggregators.
- Routes with unknown coverage: probe per request, or compute the coverage once at index time, and for which flag levels.
- Verification design (8.2, item 6).
- How live and stored results are reconciled when they disagree.
- Coverage union when several ivoids share a route (10.2).
- Whether the `specmid` helpers cover only named filters or coarse band names as well.

## 18. Next step

Module and function layout of the package: registry access, index reading and writing, classification, coverage tests, provider queries and result assembly, with the registry-specific code isolated as in section 5.
