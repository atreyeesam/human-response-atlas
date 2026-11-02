# Methods: evidence discovery engine (v0.8)

This document describes exactly how Human Response Atlas searches, combines and classifies
evidence. The same text, with the exact queries used, is included in every evidence-gap report.

## 1. Sources

| Source | What is used | How | Licence / terms |
|---|---|---|---|
| ChEMBL | Standardised identifier, synonyms, trade names, mechanism | REST API `molecule/search`, `mechanism` | CC BY-SA 3.0 |
| ClinPGx | Curated gene–drug annotations, evidence levels, curated ancestry | Local bulk download (`python ingest.py`) | CC BY-NC-SA 4.0 (non-commercial) |
| CPIC | Gene–drug levels and guidelines | Local copy from the CPIC API | CC0, attribution requested |
| PubMed | Publications, abstracts (processed locally), MeSH, affiliations, trial registration numbers | E-utilities `esearch` + `efetch` | NLM terms; abstracts may be copyrighted |
| Europe PMC | Publications, preprints, open-access status, per-article licence | REST `search` (`resultType=core`, cursor paging) | Europe PMC terms; per-article licences vary |
| ClinicalTrials.gov | Registered studies, site countries, enrolment, posted race/ethnicity counts, linked result papers | API v2 `/studies` | ClinicalTrials.gov terms (NLM) |

PubTator 3.0 and the optional local/paid language models are Phase 2.

## 2. Source status

Every source ends a search in one of four states, recorded in the report:

- **searched**: the request succeeded. Zero results then genuinely means none matched.
- **failed**: the source could not be reached or returned an error. This includes Europe PMC
  errors that arrive inside an HTTP 200 response.
- **not searched**: the source was switched off or has no local data.
- **unavailable**: reserved for sources that are retired.

A failed or unsearched source can never produce "Evidence not found" (see section 6).

## 3. Medicine name resolution

The typed name is matched **exactly** against ChEMBL's preferred names and synonyms. There is
no fuzzy matching, so a salt form or a similarly named compound is never substituted.

When a match is found, the search uses:

- the generic name;
- INN, USAN, BAN, JAN and other official synonyms;
- trade names;

up to 8 names in total. Research codes are not used.

If ChEMBL has no exact match, the name is searched exactly as typed, and the report says so.

## 4. Search strategy

Three evidence categories are searched in PubMed and Europe PMC. Example for clopidogrel
(names: clopidogrel, plavix):

**PubMed**

- `pgx`: `(clopidogrel[tiab] OR plavix[tiab]) AND (pharmacogen*[tiab] OR genotyp*[tiab] OR polymorphism*[tiab] OR allele*[tiab] OR "Pharmacogenetics"[MeSH] OR "Polymorphism, Genetic"[MeSH])`
- `efficacy`: `(clopidogrel[tiab] OR plavix[tiab]) AND (randomized controlled trial[pt] OR meta-analysis[pt] OR systematic review[pt])`
- `safety`: `(clopidogrel[tiab] OR plavix[tiab]) AND (adverse effects[sh] OR "Drug-Related Side Effects and Adverse Reactions"[MeSH] OR "adverse event*"[tiab] OR toxicity[tiab])`

**Europe PMC**

- `pgx`: `(TITLE:clopidogrel OR ABSTRACT:clopidogrel OR TITLE:plavix OR ABSTRACT:plavix) AND (ABSTRACT:pharmacogen* OR ABSTRACT:genotyp* OR ABSTRACT:polymorphism* OR ABSTRACT:allele*)`
- `efficacy`: `(TITLE:clopidogrel OR ABSTRACT:clopidogrel OR TITLE:plavix OR ABSTRACT:plavix) AND (PUB_TYPE:"randomized controlled trial" OR PUB_TYPE:"meta-analysis" OR PUB_TYPE:"systematic review")`
- `safety`: `(TITLE:clopidogrel OR ABSTRACT:clopidogrel OR TITLE:plavix OR ABSTRACT:plavix) AND (ABSTRACT:"adverse event" OR ABSTRACT:"adverse events" OR ABSTRACT:toxicity OR MESH:"Drug-Related Side Effects and Adverse Reactions")`

**ClinicalTrials.gov:** `query.intr=clopidogrel OR plavix` (all registered studies listing the
medicine as an intervention).

**Retrieval cap.** By default up to 5,000 records are retrieved per query and category (PubMed allows at most
9,999 per query), and up to 2,000 trials. The report always shows both the number of hits each source reported and the number
retrieved. Where the source reported more, the source is marked **truncated**, and every count
is a lower bound. Use `--max` and `--max-trials` to raise the caps.

## 5. De-duplication

Records from different databases are linked into one study when any of these match:

- **PMID**;
- **DOI**, ignoring case and any `doi.org` prefix;
- **PMCID**;
- **trial registration number**. A trial is linked to a paper only through:
  - the paper's own registration number (PubMed's DataBank field, or "Trial registration: NCT…"
    in the abstract); or
  - the trial's **RESULT/DERIVED** references.

  BACKGROUND references cite other studies, so they never link.
- **normalised title and the same year**, for publications only and only when the title is longer
  than 25 characters. This links preprints to their published versions.

Links are transitive: if A matches B and B matches C, all three are one study. Each study keeps
every source reference, so provenance is never lost.

## 6. Evidence classification (rules v2, Atlas v0.8)

The rules are in `hra/classify.py`; every assignment returns the evidence that supports it.

**gene (pharmacogenomic association)**

- **Established evidence:** a *published* CPIC guideline rates the pair level A or B
  (provisional levels without a guideline do not count), or a ClinPGx summary annotation is
  level 1A or 1B. Evidence: the guideline and/or the 1A/1B annotations.
- **Conflicting evidence:** not established, and *within one ClinPGx summary annotation*
  (the same variant or haplotype and the same outcome) at least 2 significant and 2
  non-significant study results, with non-significant results at least one third of those that
  state significance. Evidence: that annotation, with the PubMed IDs on each side.
- **Emerging evidence:** strongest ClinPGx level 2A or 2B. Evidence: those annotations.
- **Limited indexed evidence:** only ClinPGx level 3 or 4 annotations.
- **Not assessed:** ClinPGx not searched or failed.

**medicine and evidence type (pgx, efficacy, safety)**

- **Not assessed (search):** every source for that type failed or was not searched.
- **Evidence not found:** nothing relevant, and every source was searched successfully. Never
  given after a partial search.
- **Limited indexed evidence:** 1 to 4 relevant unique studies.
- **pgx:** otherwise the strongest gene classification, with that gene as evidence.
- **Efficacy and safety:** more than 4 relevant studies are **Not assessed (findings not yet
  evaluated)**. The engine counts studies and study designs but does not judge what they
  found, so it never calls them established, emerging or conflicting by itself.
- **Human-reviewed conclusions:** a reviewer can add a row to
  `verification/reviewed_conclusions.csv` (medicine, category, classification, supporting
  PubMed IDs, summary, reviewer, date). Rows without supporting PMIDs or a reviewer are ignored.
  The result is labelled "human-reviewed" and cites those PMIDs.
- Registered trials count as efficacy evidence only when they have posted results or a linked
  results publication; the others are listed separately.

**Changes from v1 (v0.7):** v1 called efficacy and safety "Established" from counts of trials and
reviews, judged "Conflicting" across different variants and outcomes, called level 3–4
annotations "Emerging", accepted provisional CPIC levels, and counted trial registrations as
evidence. All five are corrected.

## 6a. Evidence integrity audit

Every report runs `hra/audit.py` and shows the result ("Evidence check"). It verifies that:

- every population and geography count equals the number of studies listed as its evidence,
  and participant totals equal the sum of their cited trials;
- every cited study exists in the report;
- every category lists its supporting studies, and human-reviewed categories cite PMIDs;
- "Evidence not found" never follows a partial search;
- every gene classification cites a guideline or annotation;
- every extracted value appears in its own quote.

Any failure is listed and the report is marked as failing the check.

## 7. Extraction (hybrid pipeline, Phase 1: rules)

Every extracted value records:

- the study it belongs to;
- the field;
- the value exactly as stated;
- the source and its identifier;
- a short quote;
- its character position in the source text;
- the rule version that produced it;
- a verification status.

| Field | Method | Status |
|---|---|---|
| `curated_ancestry_group` | ClinPGx study parameters | curator-reviewed (ClinPGx) |
| `registry_race_ethnicity` | ClinicalTrials.gov posted baseline results, registry wording kept | source-structured |
| `registered_site_country`, `registered_enrollment` | ClinicalTrials.gov registry fields | source-structured |
| `indexed_place` | PubMed MeSH geographic headings, excluding "/ethnology" | source-structured (not proof of recruitment) |
| `author_affiliation_country` | `rule:affiliation_country_v1` | unverified |
| `stated_sample_size` | `rule:sample_size_v1` | unverified |
| `stated_population` | `rule:population_description_v1`: the descriptor exactly as written | unverified |
| `stated_recruitment_country` | `rule:recruitment_place_v1`: countries named after "recruited/conducted/enrolled in…" | unverified |
| `stated_effect_estimate` | `rule:effect_estimate_v1`: OR/HR/RR with 95% CI | unverified; needs human review |

Rules record only what a text states. A population description is never mapped to an
ancestry group. Ancestry is never derived from nationality, study location or author
affiliation. Missing values stay missing.

Abstracts are processed on the user's computer and are not stored in reports; reports keep
only short quotes so that each value can be checked.

## 8. Population and geography layers

Kept separate in every report and view:

1. **Registered trial sites:** the registry's site countries.
2. **Recruitment country stated in an abstract:** rule-extracted, unverified.
3. **Author locations.**
4. **Populations described in reports:** as written.
5. **Places indexed by PubMed:** never treated as proof of recruitment.

The number of studies with no information in any layer is also reported.

## 9. Scientific benchmark

`python -m hra.benchmark run` (live) searches five medicines and writes
`verification/benchmark/benchmark_report.md` and `benchmark.json`. Reference standards are
independent of the engine:

| | What is measured | Reference standard |
|---|---|---|
| A. Search completeness | Recall of the literature search (PubMed + Europe PMC, without ClinPGx); missed PMIDs listed | Studies cited by ClinPGx curators for the medicine (clopidogrel 215, warfarin 274, fluorouracil 182, tamoxifen 80, bisoprolol 1 in the 2026-10-05 release); landmark studies |
| B. De-duplication | Precision and recall of title matching with identifiers hidden; studies merging several PMIDs listed for review | Records known to be the same because they share a PMID |
| C. Extraction (automatic) | Sample size and population precision/recall | ClinPGx curated cohort sizes and biogeographical groups. Approximate: curators read the full text, rules read only abstracts. A benchmark-only word list maps descriptors to groups for scoring; the product never uses it |
| D. Extraction (manual gold standard) | Precision, recall and F1 for all four extracted fields | A reviewer annotates `annotation_worksheet.csv` (40 abstracts sampled with a fixed seed). Predictions are kept in a separate file so the reviewer is blinded. Score with `python -m hra.benchmark score verification/benchmark/annotation_worksheet.csv`. The worksheet holds full abstracts, so it stays on your computer (excluded from Git) |
| E. Runtime and cost | Seconds per source; paid-service cost | £0 (rules only) |

## 10. Validation

`verification/validation_v07.csv` lists manually reviewed expected results:

- established genes from CPIC;
- landmark studies that a live search must find;
- name resolution;
- bisoprolol's trial evidence.

Run `python -m hra.validate` (live) or `python -m hra.validate --offline`. The output is in
`verification/validation_report.md`.

## 11. Known limitations

- What efficacy and safety studies found is not yet evaluated, so they stay "Not assessed" unless
  a person records a reviewed conclusion.
- Gene associations outside ClinPGx are not yet extracted from abstracts (PubTator, Phase 2).
- Extraction precision and recall are measured by the benchmark, but the manual gold standard
  needs a reviewer to annotate the worksheet. Until then, treat extracted values as leads to check.
