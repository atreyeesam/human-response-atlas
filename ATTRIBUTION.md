# Data attribution and licences

Human Response Atlas does not ship third-party evidence data. The only bundled
third-party file is the public-domain Natural Earth map. Running `python ingest.py` (or
pressing **Download data** in the app) downloads it from the sources
below into `data/live/`. Anyone who redistributes that folder, an export from the app,
or anything derived from them must keep the attribution below.

## ClinPGx (incorporating PharmGKB®)

- **What we use:** summary (clinical) annotations, their evidence lists and PMIDs, and
  variant-annotation study parameters (study size, study type, biogeographical group),
  from the bulk downloads `summaryAnnotations.zip` and `variantAnnotations.zip` at
  `https://api.clinpgx.org/v1/download/file/data/`.
- **Licence:** [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International
  (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/), as stated in the
  `LICENSE.txt` inside both downloads (checked on the 2026-10-05 release, downloaded
  2026-10-31). The app reads the licence from that file on every download, so if ClinPGx
  changes it, the app follows. Data usage policy: <https://www.clinpgx.org/page/dataUsagePolicy>.
  How to cite: <https://www.clinpgx.org/page/citingClinpgx>.
- **What the ClinPGx licence file requires** (its own words, summarised):
  1. *Attribution* — credit ClinPGx, link the licence, say what was changed, and never
     suggest ClinPGx endorses you. The app footer, the About tab, `data/live/manifest.json`
     and every export's `ATTRIBUTION_AND_LICENCE.txt` do this.
  2. *NonCommercial* — "You may not use the material for commercial purposes." "Under no
     circumstances can ClinPGx data be sold for other's private or commercial use."
     Commercial use (for example inside a company's product or paid service) needs separate
     permission from ClinPGx.
  3. *ShareAlike* — if you distribute anything altered or derived from ClinPGx data, "all
     recipients shall first agree to be subject to this license. Proof of such agreement
     shall be made available to ClinPGx." This goes beyond the standard CC BY-NC-SA terms:
     keep a record of who received exports and that they accepted the licence.
  The app's own **code** can be licensed separately; the **data** cannot be relicensed.
- **Correction:** versions 0.2–0.4 of the Atlas described this data as CC BY-SA 4.0, based
  on secondary sources. The licence file shipped with the data says CC BY-NC-SA 4.0. That
  file is authoritative.
- **Changes we make:** rows are filtered, joined to study parameters and aggregated by
  biogeographical group (distinct PMIDs; approximate cohort sizes). Old `pharmgkb.org`
  links in the files are rewritten to `clinpgx.org`.
- **Citation:** Whirl-Carrillo M, Huddart R, Gong L, et al. An evidence-based framework
  for evaluating pharmacogenomics knowledge for personalized medicine. *Clin Pharmacol
  Ther.* 2021;110(3):563-572. doi:[10.1002/cpt.2350](https://doi.org/10.1002/cpt.2350)
- The licence text that ships inside each ClinPGx download is saved verbatim to
  `data/live/upstream_licences/`.
- **Fair use of the service:** ClinPGx asks API users to stay at or below 2 requests per
  second and to contact them before any more-than-trivial use. The ingest script makes 2
  ClinPGx requests, spaced 0.6 s apart. If the Atlas is hosted publicly or refreshed
  automatically, email feedback@clinpgx.org first.

## CPIC® (Clinical Pharmacogenetics Implementation Consortium)

- **What we use:** gene–drug pairs (`/v1/pair_view`), guideline publications
  (`/v1/publication`), guideline names (`/v1/guideline`) and the latest data release
  number (`/v1/change_log`) from the CPIC API, `https://api.cpicpgx.org/v1/`
  (override with the `CPIC_API` environment variable if CPIC moves it).
- **Licence:** [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) (public
  domain). CPIC nonetheless asks users to:
  1. acknowledge that the primary source is www.clinpgx.org;
  2. cite the relevant CPIC guideline publication(s) — the app links them per pair;
  3. state that CPIC guidelines and content are subject to updates, and that users should
     check https://www.clinpgx.org/cpic for the current content;
  4. **not** reproduce the CPIC logo or acronym on another website or in advertising
     without NIH permission. The Atlas uses the name only to identify the data source,
     never the logo;
  5. cite content as "CPIC®. URL [date accessed]";
  6. for API/database content, cite the URL, the date accessed and the version number.
     These are recorded in `manifest.json` and in every export.
- **Disclaimer:** CPIC's full disclaimer is in its
  [licence file](https://github.com/cpicpgx/cpic-data/blob/main/LICENSE.md). In short,
  CPIC data must be read alongside the guidelines, may lag the guideline pages, and is not
  a substitute for clinical judgement.
- CPIC® is a registered service mark of the U.S. Department of Health & Human Services.

## PubMed / MEDLINE (U.S. National Library of Medicine)

- **What we use:** for every PMID linked from ClinPGx, the publication year, journal,
  publication types, MeSH geographic headings and author affiliations, retrieved with
  NCBI E-utilities (`efetch`, `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`).
- **How it's used:** MeSH geographic headings give the *study location*. Author
  affiliations give the *research-team location*. Publication types give the *study
  design*. Nothing is used to infer ancestry or nationality.
- **Terms:** [NLM terms and conditions](https://www.nlm.nih.gov/databases/download/terms_and_conditions.html)
  and [NCBI policies](https://www.ncbi.nlm.nih.gov/home/about/policies/). Required credit:
  "Courtesy of the U.S. National Library of Medicine". NLM does not endorse or verify this
  product. The app and every export carry this statement.
- **Fair use:** NCBI allows up to 3 requests per second without an API key. The ingest
  script sends 200 PMIDs per request, spaced 0.6 s apart, identifies itself as
  `HumanResponseAtlas`, and caches results in `data/cache/pubmed.json`. Set the
  `NCBI_EMAIL` environment variable to your email so NCBI can contact you if needed, and
  optionally `NCBI_API_KEY`.

## ChEMBL (EMBL-EBI)

- **What we use:** each medicine's identifier, preferred name, official synonyms, trade names,
  maximum development phase and mechanism of action, from the ChEMBL REST API at search time.
- **Licence:** [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). Credit ChEMBL
  and EMBL-EBI. Anything redistributed that is derived from ChEMBL data must stay under the same
  licence. Cite: Zdrazil B, et al. The ChEMBL Database in 2023. *Nucleic Acids Res* 2024;52:D1180–D1192.

## Europe PMC

- **What we use:** search results (bibliographic metadata, open-access flags, per-article
  licence where stated) and abstracts, which are processed locally and not republished.
- **Terms:** <https://europepmc.org/Copyright>. Licences vary by article and are recorded on
  each record in the report.

## ClinicalTrials.gov (U.S. National Library of Medicine)

- **What we use:** registered studies listing the medicine as an intervention: identifiers,
  status, design, enrolment, site countries, posted baseline race/ethnicity counts (kept in the
  registry's own categories) and the trial's own result papers.
- **Terms:** <https://clinicaltrials.gov/about-site/terms-conditions>. Records are provided by
  study sponsors. Credit ClinicalTrials.gov, and do not present records as verified or endorsed
  by NLM.

## Natural Earth (country boundaries)

- `data/geo/countries.geojson` is simplified from Natural Earth 1:50m Admin 0 countries.
  It is **public domain** ([terms](https://www.naturalearthdata.com/about/terms-of-use/);
  copy in `data/geo/NATURAL_EARTH_LICENSE.md`). The map is for display only and takes no
  position on disputed borders.

## One-line credit for slides or papers

> Pharmacogenomic annotations from ClinPGx (www.clinpgx.org; PharmGKB® and CPIC®),
> CC BY-NC-SA 4.0 and CC0 respectively, snapshot *[date from manifest.json]*; bibliographic
> data courtesy of the U.S. National Library of Medicine; map from Natural Earth.
> Processed by Human Response Atlas.
