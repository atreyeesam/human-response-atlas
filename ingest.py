"""Download and normalise ClinPGx and CPIC data for the Human Response Atlas.

Run from the project folder:

    python ingest.py

What it fetches
---------------
ClinPGx (https://www.clinpgx.org, maintained API host: api.clinpgx.org)
  * summaryAnnotations.zip  - gene-drug summary (clinical) annotations, their level
                              of evidence, the evidence items behind them (with PMIDs)
                              and the "Latest History Date" of each annotation.
  * variantAnnotations.zip  - the individual study-level variant annotations and
                              their study parameters (cohort size, study type and
                              biogeographical group).
  Licence: read from the LICENSE.txt inside each download. As of the 2026-10-05
  release this is CC BY-NC-SA 4.0 (Attribution-NonCommercial-ShareAlike).

PubMed (NCBI E-utilities, eutils.ncbi.nlm.nih.gov)
  * efetch for every PMID linked from ClinPGx: publication year and type, MeSH
    geographic indexing (study location) and author affiliations (team location).
  Courtesy of the U.S. National Library of Medicine. Cached in data/cache/.

CPIC (Clinical Pharmacogenetics Implementation Consortium)
  * /v1/pair_view           - gene-drug pairs with CPIC level, guideline and PMIDs.
  * /v1/publication         - guideline publications (PMID, year, DOI).
  * /v1/change_log          - used only to record the CPIC data release number.
  Licence: CC0 1.0, with CPIC's attribution requests (see ATTRIBUTION.md).

Everything is written to data/live/ together with manifest.json, which records
every URL, the date accessed, the upstream release dates/versions, file
checksums and the licence that applies. The licence text shipped inside the
ClinPGx downloads is copied verbatim into data/live/upstream_licences/.

Requests are spaced well under ClinPGx's limit of 2 requests per second.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

__version__ = "0.3.0"

CLINPGX_API = os.environ.get("CLINPGX_API", "https://api.clinpgx.org/v1").rstrip("/")
CPIC_API = os.environ.get("CPIC_API", "https://api.cpicpgx.org/v1").rstrip("/")

CLINPGX_FILES = {
    "summaryAnnotations": f"{CLINPGX_API}/download/file/data/summaryAnnotations.zip",
    "variantAnnotations": f"{CLINPGX_API}/download/file/data/variantAnnotations.zip",
}
CPIC_ENDPOINTS = {
    "pair_view": f"{CPIC_API}/pair_view",
    "publication": f"{CPIC_API}/publication?guidelineid=not.is.null"
                   "&select=guidelineid,pmid,pmcid,doi,title,year,journal,url",
    "guideline": f"{CPIC_API}/guideline?select=id,name,url,clinpgxid",
    "change_log": f"{CPIC_API}/change_log?select=date,deployedrelease"
                  "&deployedrelease=not.is.null&order=date.desc&limit=1",
}

CPIC_RELEASES = "https://api.github.com/repos/cpicpgx/cpic-data/releases/latest"

LICENCES = {
    "clinpgx": {
        "name": "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International "
                "(CC BY-NC-SA 4.0)",
        "short": "CC BY-NC-SA 4.0",
        "url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "policy": "https://www.clinpgx.org/page/dataUsagePolicy",
        "cite": "https://www.clinpgx.org/page/citingClinpgx",
        "detected_from": "default (no licence file read yet)",
    },
    "pubmed": {
        "name": "NLM terms and conditions (bibliographic data courtesy of the U.S. National Library of Medicine)",
        "url": "https://www.nlm.nih.gov/databases/download/terms_and_conditions.html",
        "policy": "https://www.ncbi.nlm.nih.gov/home/about/policies/",
    },
    "cpic": {
        "name": "CC0 1.0 Universal (public domain dedication), with CPIC attribution requests",
        "url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "policy": "https://github.com/cpicpgx/cpic-data/blob/main/LICENSE.md",
    },
}

USER_AGENT = f"HumanResponseAtlas/{__version__} (research prototype; python-urllib)"
MIN_SECONDS_BETWEEN_REQUESTS = 0.6   # ClinPGx asks for <= 2 requests per second
_last_request = 0.0

LEVEL_ORDER = ["1A", "1B", "2A", "2B", "3", "4"]

# The nine ClinPGx biogeographical groups plus the two non-group labels it uses.
BIOGEO_GROUPS = ["African American/Afro-Caribbean", "American", "Central/South Asian",
                 "East Asian", "European", "Latino", "Near Eastern", "Oceanian",
                 "Sub-Saharan African", "Multiple groups", "Unknown"]
_BIOGEO_LOOKUP = {g.lower(): g for g in BIOGEO_GROUPS}
IN_VITRO = "In vitro (no participants)"


def clean_population(raw: str) -> list[str]:
    """Recognised ClinPGx groups in a 'Biogeographical Groups' value.

    The field can carry a free-text description after the group, e.g.
    'Multiple groups, 87.8% white, 7% black'. Only recognised labels are kept;
    the description is preserved separately as population_detail.
    """
    tokens = [t.strip().strip('"').strip() for t in re.split(r"[;,]", raw or "")]
    found = [_BIOGEO_LOOKUP[t.lower()] for t in tokens if t.lower() in _BIOGEO_LOOKUP]
    if found:
        return list(dict.fromkeys(found))
    if any(t.lower() == "in vitro" for t in tokens):
        return [IN_VITRO]
    return ["Unknown"]


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _get(url: str, accept: str = "*/*", retries: int = 3, data: bytes | None = None) -> bytes:
    """GET (or POST when `data` is given) with polite spacing and retries."""
    global _last_request
    for attempt in range(1, retries + 1):
        wait = MIN_SECONDS_BETWEEN_REQUESTS - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, data=data,
                                     headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                _last_request = time.monotonic()
                return resp.read()
        except urllib.error.HTTPError as e:
            _last_request = time.monotonic()
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(5 * attempt)
                continue
            raise RuntimeError(f"{url} returned HTTP {e.code}") from e
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(3 * attempt)
                continue
            raise RuntimeError(f"Could not reach {url}: {e.reason}") from e
    raise RuntimeError(f"Failed to fetch {url}")


# --------------------------------------------------------------------------- #
# Parsing helpers (pure functions, unit-tested with fixtures)
# --------------------------------------------------------------------------- #
def _norm(col: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", col.strip().lower()).strip("_")


def _require(df: pd.DataFrame, cols: list[str], source: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"{source}: expected columns {missing} are missing. ClinPGx may have changed "
            f"its file format; columns found: {list(df.columns)}")


def read_zip_tables(blob: bytes) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Return ({table_name: DataFrame}, {text_file_name: text}) from a ClinPGx zip."""
    tables, texts = {}, {}
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for info in zf.infolist():
            name = Path(info.filename).name
            if info.is_dir() or not name:
                continue
            if name.endswith(".tsv"):
                with zf.open(info) as fh:
                    df = pd.read_csv(fh, sep="\t", dtype=str, keep_default_na=False,
                                     quoting=3, on_bad_lines="warn")
                df.columns = [_norm(c) for c in df.columns]
                tables[name[:-4]] = df
            elif name.lower().endswith((".txt", ".md")):
                texts[name] = zf.read(info).decode("utf-8", errors="replace")
    return tables, texts


def release_date(texts: dict[str, str]) -> str | None:
    """ClinPGx zips contain an empty marker file such as CREATED_2026-10-01.txt."""
    for name in texts:
        m = re.match(r"CREATED_(\d{4}-\d{2}-\d{2})", name)
        if m:
            return m.group(1)
    return None


def _split(value: str, pattern: str = r"\s*;\s*") -> list[str]:
    return [v for v in re.split(pattern, value or "") if v.strip()]


def parse_summary_annotations(tables: dict[str, pd.DataFrame]):
    """Normalise summary annotations + their evidence list.

    Returns (associations, evidence). Accepts the current 'summary_*' file names
    and the older PharmGKB 'clinical_*' names.
    """
    ann = tables.get("summary_annotations", tables.get("clinical_annotations"))
    ev = tables.get("summary_ann_evidence", tables.get("clinical_ann_evidence"))
    if ann is None or ev is None:
        raise ValueError("summaryAnnotations.zip: summary_annotations.tsv / "
                         "summary_ann_evidence.tsv not found")
    for df in (ann, ev):
        df.rename(columns={"clinical_annotation_id": "summary_annotation_id"}, inplace=True)
    ann = ann.rename(columns={"latest_history_date_yyyy_mm_dd": "latest_history_date",
                              "drug_s": "drugs", "phenotype_s": "phenotypes",
                              "variant_haplotypes": "variant"})
    _require(ann, ["summary_annotation_id", "variant", "gene", "level_of_evidence", "score",
                   "phenotype_category", "pmid_count", "evidence_count", "drugs",
                   "phenotypes", "latest_history_date", "url"], "summary_annotations.tsv")
    _require(ev, ["summary_annotation_id", "evidence_id", "evidence_type",
                  "evidence_url", "pmid"], "summary_ann_evidence.tsv")

    ann = ann.copy()
    ann["drug"] = ann["drugs"].map(lambda s: [d.lower() for d in _split(s)])
    ann["gene"] = ann["gene"].map(_split)
    ann = ann.explode("drug").explode("gene").dropna(subset=["drug", "gene"])
    if "specialty_population" not in ann:
        ann["specialty_population"] = ""
    associations = pd.DataFrame({
        "summary_annotation_id": ann["summary_annotation_id"],
        "drug": ann["drug"],
        "gene": ann["gene"],
        "variant": ann["variant"],
        "outcome": ann["phenotype_category"].replace("", "Unspecified"),
        "phenotypes": ann["phenotypes"],
        "level_of_evidence": ann["level_of_evidence"],
        "score": pd.to_numeric(ann["score"], errors="coerce"),
        "pmid_count": pd.to_numeric(ann["pmid_count"], errors="coerce"),
        "evidence_count": pd.to_numeric(ann["evidence_count"], errors="coerce"),
        "latest_history_date": ann["latest_history_date"],
        "specialty_population": ann["specialty_population"],
        "source_url": ann["url"].str.replace("www.pharmgkb.org", "www.clinpgx.org", regex=False),
    }).drop_duplicates().reset_index(drop=True)

    evidence = ev[["summary_annotation_id", "evidence_id", "evidence_type",
                   "evidence_url", "pmid"]].copy()
    evidence["evidence_url"] = evidence["evidence_url"].str.replace(
        "www.pharmgkb.org", "www.clinpgx.org", regex=False)
    return associations, evidence.drop_duplicates().reset_index(drop=True)


def parse_study_populations(tables: dict[str, pd.DataFrame], evidence: pd.DataFrame) -> pd.DataFrame:
    """Link summary-annotation evidence -> variant annotation -> study parameters.

    One output row per (summary annotation, variant annotation, study parameter set,
    biogeographical group). PMIDs come from the evidence list.
    """
    sp = tables.get("study_parameters")
    if sp is None:
        raise ValueError("variantAnnotations.zip: study_parameters.tsv not found")
    _require(sp, ["study_parameters_id", "variant_annotation_id", "study_type",
                  "study_cases", "study_controls", "biogeographical_groups"],
             "study_parameters.tsv")
    sp = sp.copy()
    sp["biogeographical_group"] = sp["biogeographical_groups"].map(clean_population)
    sp["population_detail"] = sp["biogeographical_groups"].str.strip().str.strip('"')
    sp = sp.explode("biogeographical_group")

    # Reported statistical significance of each variant annotation (yes / no / not stated)
    sig = []
    for name in ("var_drug_ann", "var_pheno_ann", "var_fa_ann"):
        t = tables.get(name)
        if t is not None and "variant_annotation_id" in t and "significance" in t:
            sig.append(t[["variant_annotation_id", "significance"]])
    if sig:
        sig = pd.concat(sig).drop_duplicates("variant_annotation_id")
        sp = sp.merge(sig, on="variant_annotation_id", how="left")
    else:
        sp["significance"] = ""

    linked = evidence.merge(sp, left_on="evidence_id", right_on="variant_annotation_id",
                            how="inner")
    out = pd.DataFrame({
        "summary_annotation_id": linked["summary_annotation_id"],
        "variant_annotation_id": linked["variant_annotation_id"],
        "evidence_type": linked["evidence_type"],
        "pmid": linked["pmid"],
        "study_parameters_id": linked["study_parameters_id"],
        "study_type": linked["study_type"],
        "study_cases": pd.to_numeric(linked["study_cases"], errors="coerce"),
        "study_controls": pd.to_numeric(linked["study_controls"], errors="coerce"),
        "population": linked["biogeographical_group"],
        "population_detail": linked["population_detail"],
        "significance": linked["significance"].fillna("").str.lower(),
    })
    return out.drop_duplicates().reset_index(drop=True)


def parse_cpic(pairs: list[dict], publications: list[dict], guidelines: list[dict]):
    pairs_df = pd.DataFrame(pairs)
    _require(pairs_df, ["pairid", "drugname", "genesymbol", "cpiclevel"], "CPIC pair_view")
    for col in ("guidelinename", "guidelineurl", "clinpgxlevel", "pgxtesting", "pmids",
                "provisional", "usedforrecommendation"):
        if col not in pairs_df:
            pairs_df[col] = None
    pairs_df = pd.DataFrame({
        "cpic_pair_id": pairs_df["pairid"],
        "drug": pairs_df["drugname"].str.lower(),
        "gene": pairs_df["genesymbol"],
        "cpic_level": pairs_df["cpiclevel"],
        "cpic_provisional": pairs_df["provisional"],
        "clinpgx_top_level": pairs_df["clinpgxlevel"],
        "fda_label_testing": pairs_df["pgxtesting"],
        "cpic_guideline": pairs_df["guidelinename"],
        "cpic_guideline_url": pairs_df["guidelineurl"],
        "cpic_pmids": pairs_df["pmids"].map(
            lambda v: ";".join(map(str, v)) if isinstance(v, list) else (v or "")),
    })
    pubs = pd.DataFrame(publications)
    guides = pd.DataFrame(guidelines)
    if not pubs.empty and not guides.empty:
        pubs = pubs.merge(guides.rename(columns={"id": "guidelineid", "name": "guideline",
                                                 "url": "guideline_url"}),
                          on="guidelineid", how="left")
    return pairs_df, pubs


_CC_NAMES = {"by": "Attribution", "nc": "NonCommercial", "sa": "ShareAlike", "nd": "NoDerivatives"}


def detect_licence(texts: dict[str, str]) -> dict | None:
    """Read the Creative Commons licence named in ClinPGx's own LICENSE.txt."""
    for name, text in texts.items():
        m = re.search(r"creativecommons\.org/licenses/([a-z-]+)/(\d\.\d)", text, re.I)
        if not m:
            continue
        code, ver = m.group(1).lower(), m.group(2)
        long = "-".join(_CC_NAMES.get(p, p) for p in code.split("-"))
        return {"name": f"Creative Commons {long} {ver} International (CC {code.upper()} {ver})",
                "short": f"CC {code.upper()} {ver}",
                "url": f"https://creativecommons.org/licenses/{code}/{ver}/",
                "policy": "https://www.clinpgx.org/page/dataUsagePolicy",
                "cite": "https://www.clinpgx.org/page/citingClinpgx",
                "noncommercial": "nc" in code.split("-"),
                "sharealike": "sa" in code.split("-"),
                "detected_from": name}
    return None


def pubmed_tables(records: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Flatten cached PubMed records into (pubmed.csv, study_locations.csv).

    study_locations keeps the two bases apart: 'study location' comes only from
    NLM MeSH geographic indexing; 'research team' only from author affiliations.
    """
    pubs, locs = [], []
    for pmid, r in records.items():
        pubs.append({"pmid": pmid, "year": r.get("year", ""), "title": r.get("title", ""),
                     "journal": r.get("journal", ""),
                     "pub_types": ";".join(r.get("pub_types", [])),
                     "mesh_indexed": bool(r.get("mesh_indexed")),
                     "found_in_pubmed": not r.get("missing", False),
                     "geo_terms": ";".join(r.get("geo_terms", [])),
                     "regions": ";".join(r.get("regions", [])),
                     "origin_terms": ";".join(r.get("origin_terms", []))})
        for iso in r.get("study_countries", []):
            locs.append({"pmid": pmid, "iso3": iso, "basis": "study location"})
        for iso in r.get("affiliation_countries", []):
            locs.append({"pmid": pmid, "iso3": iso, "basis": "research team"})
    return (pd.DataFrame(pubs, columns=["pmid", "year", "title", "journal", "pub_types",
                                        "mesh_indexed", "found_in_pubmed", "geo_terms",
                                        "regions", "origin_terms"]),
            pd.DataFrame(locs, columns=["pmid", "iso3", "basis"]))


def best_level(levels) -> str:
    present = [lv for lv in LEVEL_ORDER if lv in set(levels)]
    return present[0] if present else ""


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _json(url: str):
    return json.loads(_get(url, accept="application/json").decode("utf-8"))


def _post(url: str, form: dict) -> bytes:
    return _get(url, accept="application/xml", data=urllib.parse.urlencode(form).encode())


def run(out_dir: Path | str = Path(__file__).parent / "data" / "live", log=print,
        with_pubmed: bool = True, pubmed_cache: Path | None = None) -> dict:
    out_dir = Path(out_dir)
    tmp_dir = out_dir.with_name(out_dir.name + "_incoming")
    if tmp_dir.exists():
        _rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    (tmp_dir / "upstream_licences").mkdir(exist_ok=True)
    accessed = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = {"atlas_ingest_version": __version__, "accessed_utc": accessed,
                "sources": {}, "licences": LICENCES, "outputs": {}}

    # ---- ClinPGx ------------------------------------------------------------
    clinpgx_tables, clinpgx_meta, licence_texts = {}, {}, {}
    for key, url in CLINPGX_FILES.items():
        log(f"Downloading ClinPGx {key} …")
        blob = _get(url)
        tables, texts = read_zip_tables(blob)
        clinpgx_tables.update(tables)
        for name, text in texts.items():
            if not name.startswith("CREATED_"):
                licence_texts[f"clinpgx_{key}_{name}"] = text
                (tmp_dir / "upstream_licences" / f"clinpgx_{key}_{name}").write_text(text, "utf-8")
        clinpgx_meta[key] = {"url": url, "sha256": _sha256(blob), "bytes": len(blob),
                             "release_date": release_date(texts),
                             "files": sorted(list(tables) + list(texts))}
    manifest["sources"]["clinpgx"] = clinpgx_meta
    detected = detect_licence(licence_texts)
    if detected:
        manifest["licences"] = {**LICENCES, "clinpgx": detected}
    else:
        log("  WARNING: no licence named in the ClinPGx download; check upstream_licences/.")

    associations, evidence = parse_summary_annotations(clinpgx_tables)
    study_pops = parse_study_populations(clinpgx_tables, evidence)

    # ---- CPIC ---------------------------------------------------------------
    log("Downloading CPIC gene–drug pairs and guideline publications …")
    pairs = _json(CPIC_ENDPOINTS["pair_view"])
    pubs = _json(CPIC_ENDPOINTS["publication"])
    guides = _json(CPIC_ENDPOINTS["guideline"])
    cpic_release = None
    try:
        cl = _json(CPIC_ENDPOINTS["change_log"])
        cpic_release = cl[0].get("deployedrelease") if cl else None
    except Exception as e:  # version number is nice-to-have, never fatal
        log(f"  (CPIC change log unavailable: {e})")
    if not cpic_release:   # fall back to the latest published CPIC database release
        try:
            rel = _json(CPIC_RELEASES)
            cpic_release = rel.get("tag_name")
            manifest["cpic_release_source"] = CPIC_RELEASES
        except Exception as e:
            log(f"  (could not read CPIC release number: {e})")
    cpic_pairs, cpic_pubs = parse_cpic(pairs, pubs, guides)
    manifest["sources"]["cpic"] = {
        "endpoints": CPIC_ENDPOINTS, "release": cpic_release,
        "pairs": len(cpic_pairs), "guideline_publications": len(cpic_pubs)}

    # ---- PubMed: study location, research-team location, design, year ------
    import pubmed
    pmids = sorted(set(evidence["pmid"]) - {""})
    if with_pubmed:
        cache_file = Path(pubmed_cache or pubmed.CACHE_FILE)
        try:
            records, stats = pubmed.enrich(pmids, _post, cache_file, log=log)
        except Exception as e:   # PubMed down: keep going with whatever is cached
            log(f"  PubMed look-up incomplete ({e}); using previously saved PubMed results.")
            cached = json.loads(cache_file.read_text("utf-8")) if cache_file.exists() else {}
            records = {p: cached[p] for p in pmids if p in cached}
            stats = {"pmids": len(pmids), "fetched_now": 0, "error": str(e),
                     "from_cache": len(records)}
    else:
        records, stats = {}, {"pmids": len(pmids), "fetched_now": 0, "skipped": True}
    pubmed_df, locations = pubmed_tables(records)
    manifest["sources"]["pubmed"] = stats

    # ---- Join CPIC onto ClinPGx associations -------------------------------
    associations = associations.merge(
        cpic_pairs[["drug", "gene", "cpic_level", "cpic_guideline", "cpic_guideline_url",
                    "cpic_pmids"]], on=["drug", "gene"], how="left")

    outputs = {
        "associations.csv": associations,
        "evidence.csv": evidence,
        "study_populations.csv": study_pops,
        "pubmed.csv": pubmed_df,
        "study_locations.csv": locations,
        "cpic_pairs.csv": cpic_pairs,
        "cpic_publications.csv": cpic_pubs,
    }
    for name, df in outputs.items():
        df.to_csv(tmp_dir / name, index=False)
        manifest["outputs"][name] = {"rows": int(len(df))}
    (tmp_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")

    # Swap in atomically-ish so a failed run never leaves half a dataset behind.
    if out_dir.exists():
        backup = out_dir.with_name(out_dir.name + "_previous")
        if backup.exists():
            _rmtree(backup)
        out_dir.rename(backup)
    tmp_dir.rename(out_dir)
    log(f"Done. {len(associations):,} gene–drug annotation rows, "
        f"{len(study_pops):,} study-population links, {len(cpic_pairs):,} CPIC pairs → {out_dir}")
    return manifest


def _rmtree(p: Path) -> None:
    for child in p.iterdir():
        _rmtree(child) if child.is_dir() else child.unlink()
    p.rmdir()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(Path(__file__).parent / "data" / "live"),
                    help="output folder (default: data/live)")
    ap.add_argument("--skip-pubmed", action="store_true",
                    help="skip PubMed look-ups (the world map will then be empty)")
    args = ap.parse_args(argv)
    try:
        run(args.out, with_pubmed=not args.skip_pubmed)
    except Exception as e:
        print(f"\nIngest failed: {e}\nYour previous data (if any) has not been changed.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
