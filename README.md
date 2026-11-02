# Human Response Atlas — v0.8

**Open-source research prototype: a global map of where pharmacogenomic evidence comes from, and who is missing from it.**

## Will this medicine work for me?

The app opens on a simple question page for anyone, not just researchers. You choose a
medicine and, if you like, the ancestry groups that describe your family and the country
you live in. The page then answers three questions in plain language:

1. **Do genes affect this medicine?** For example, whether an expert prescribing guideline
   (CPIC) exists, with a link to it.
2. **Have people like you been studied?** For example, "2 of 215 studies included people of
   Central or South Asian ancestry", compared with the best-studied group.
3. **Where was the research done?** Including your country, with the share of studies
   that have a recorded location.

It then says what this means for you:

- the evidence cannot predict one person's response;
- don't change a medicine without your doctor or pharmacist;
- ask whether a genetic test is relevant when a guideline exists;
- being under-studied is a research gap, not a sign of danger.

Your answers are not saved. The page gives no individual prediction or medical advice.

## New in v0.8: evidence integrity and benchmarking

- **Corrected classification rules (v2).** Efficacy and safety are no longer called
  "Established" from study counts; they stay "Not assessed" until a person records a reviewed
  conclusion with its PubMed IDs. "Conflicting" is now judged within one variant and outcome.
  Details in [docs/METHODS.md](docs/METHODS.md#6-evidence-classification-rules-v2-atlas-v08).
- **Every claim is traceable.** Every gene, category, population and geography figure lists the
  guideline, annotation or studies behind it, and an automatic **evidence check** confirms each
  count matches its evidence.
- **Scientific benchmark.** `python -m hra.benchmark run` measures search completeness,
  de-duplication and extraction against curated and manually reviewed publications.

## Evidence discovery engine (v0.7)

The Atlas can now search beyond ClinPGx. For one medicine, the engine:

1. **Resolves the name** in ChEMBL: generic name, official synonyms and brand names. "Plavix"
   finds clopidogrel.
2. **Searches** PubMed, Europe PMC and ClinicalTrials.gov, alongside your ClinPGx and CPIC
   download, for pharmacogenomic, efficacy and safety evidence.
3. **Records the outcome for every source:** searched, failed or not searched. A failure is
   never shown as "nothing found".
4. **Retrieves every matching record** (up to 5,000 per search by default), then **removes duplicates** across databases using PMID, DOI, PMCID, trial registration number
   and title. One study found in three databases counts once and keeps all three links.
5. **Extracts, with rules,** the stated sample sizes, the populations as described, recruitment
   countries and effect estimates. Each value keeps its exact quote and is marked
   **unverified** until checked.
6. **Classifies the evidence** with written rules (v2): Established, Emerging, Conflicting, Limited
   indexed evidence, Evidence not found, or Not assessed, each with its supporting evidence.
7. **Writes a reproducible evidence-gap report:** HTML, JSON and CSV, including the exact
   search terms, dates, counts and licences.

How to use it:

- **In the app:** *Explore the evidence* → choose a medicine → **Expand evidence search** tab
  → **Search the literature**. The plain-language page then mentions what the wider search found.
- **From Terminal:**
  ```bash
  python -m hra search clopidogrel --out reports
  ```
  This prints each source's status and writes the report to `reports/`.
- **From Python** (no app needed):
  ```python
  from hra import search_medicine
  result = search_medicine("warfarin")
  result.write_report("reports")
  ```
- **Check against the validation set:**
  ```bash
  python -m hra.validate
  ```
  This runs 13 manually reviewed checks on bisoprolol, clopidogrel, warfarin, fluorouracil and
  tamoxifen (6 of them also work offline with `--offline`).

- **Run the scientific benchmark** (takes a while; needs internet and the ClinPGx download):
  ```bash
  python -m hra.benchmark run
  ```
  Results: `verification/benchmark/benchmark_report.md`.

The method is described in full in [docs/METHODS.md](docs/METHODS.md).
Phase 2 adds PubTator 3.0 annotations and an optional local language model (Ollama) with an
optional paid fallback, each measured with the same benchmark. Phase 3 adds GitHub,
continuous integration and example notebooks.

## Explore the evidence (for researchers)

In **Explore the evidence**, the top of the page states the main finding in a sentence, for
example "The studies behind ClinPGx's evidence on warfarin were done in 12 of 240
countries", with a second line on how much of that evidence comes from people of European
ancestry. Pick a **medicine** and **gene** at the top; the choice applies to every tab:

- **World map.** Countries are coloured by evidence: available, limited, or none found
  (left grey). You can switch between where studies were done and where the research
  teams are based. Click a country to see its numbers and the list of studies.
- **Who was studied.** Studies by ancestry group, and a grid of which groups were studied
  in which countries.
- **Medicine details.** The CPIC guideline, the ClinPGx evidence and the studies behind it.
- **How to read this.** Plain-language definitions and sources.

Each tab has a download button. The file includes the required attribution. Settings
(data updates, what counts as "evidence available", map colouring) are in the side panel:
click the » arrow at the top left. If no data has been downloaded yet, the app opens on a
welcome screen with a **Download data** button.

### Ancestry, location and nationality are kept apart

| | What it means | Where it comes from |
|---|---|---|
| **Ancestry** | Biogeographical group of the participants | ClinPGx curators, from each paper |
| **Study location** | Country where the study was done (or the place it concerns) | PubMed MeSH geographic indexing by NLM |
| **Research team** | Country of the authors' institutions | PubMed author affiliations |
| **Nationality** | — | **Not recorded** by any of these sources, so never shown or inferred |

None of these is ever worked out from another. An ancestry group is never placed on a
country, and a country never implies an ancestry. Studies with no country-level location
in PubMed (not yet indexed, or tagged only with a region such as "Africa South of the
Sahara") are counted and reported, never guessed.

### Evidence-quality indicators

Each country and ancestry group shows the following side by side:

- number of studies;
- approximate participants;
- best ClinPGx level of evidence;
- studies at level 1A–2B;
- trials and meta-analyses vs observational studies;
- most recent and median publication year;
- % of studies reporting a significant association.

A simple **quality signal** (Stronger / Moderate / Weaker) summarises these with a
published rule. It is not a validated score; the rule is set out in *About the data*.

> **Read this first.** The coverage only describes the studies *annotated in the loaded
> ClinPGx snapshot*. A zero means "no annotated study in this snapshot", not "no
> research exists". This is research infrastructure. It is **not** for clinical use,
> prescribing or decisions about individual patients.

---

## Running it on your computer (step by step)

You need **Python 3.10 or newer** and an internet connection.

1. **Open a terminal.**
   - Mac: press ⌘ + Space, type *Terminal*, press Enter.
   - Windows: press the Windows key, type *PowerShell*, press Enter.
2. **Go into the project folder.** Type `cd ` (with a space), drag the
   `human-response-atlas` folder onto the terminal window, then press Enter.
3. **Create a private Python environment** (one time only):
   ```bash
   python3 -m venv .venv
   ```
   On Windows, type `python` instead of `python3`.
4. **Switch it on** (every time you open a new terminal):
   - Mac: `source .venv/bin/activate`
   - Windows: `.venv\Scripts\activate`
5. **Install the parts it needs** (one time only):
   ```bash
   pip install -r requirements.txt
   ```
6. **Tell PubMed who you are** (recommended, one line). NCBI asks tools to give a contact
   email.
   - Mac: `export NCBI_EMAIL="you@example.com"`
   - Windows: `$env:NCBI_EMAIL="you@example.com"`
7. **Download the data** from ClinPGx, CPIC and PubMed. The first run takes a few
   minutes because it looks up every linked study in PubMed; later runs reuse saved
   results:
   ```bash
   python ingest.py
   ```
   It ends with a line starting `Done.`. (You can also press **Download data** in the
   app's left-hand panel.)
8. **Start the app:**
   ```bash
   streamlit run app.py
   ```
   Your browser opens at http://localhost:8501. To stop the app, go back to the terminal
   and press Ctrl + C.

**Privacy:** the app sets no tracking, sends nothing to other websites (its fonts are
served from the app itself), and stores nothing you type.

**Coming from v0.2?** Press **Update data** once. The world map needs the new PubMed
details.

**Updating the data later:** press **Update data** in the app, or
run `python ingest.py` again. If a download fails, your previous data is kept unchanged.
The last good copy before each update is kept in `data/live_previous/`.

**Running the checks:** `python -m pytest -q`. These tests use small invented files in
the ClinPGx, CPIC and PubMed formats, so they run without internet.

---

## Where the data comes from

| Source | What the Atlas takes | How | Licence |
|---|---|---|---|
| **ClinPGx** (`api.clinpgx.org`) | Gene–drug summary annotations, level of evidence, evidence items and PMIDs, latest history dates, study sizes and biogeographical groups | Bulk files `summaryAnnotations.zip` and `variantAnnotations.zip` from `/v1/download/file/data/` | **CC BY-NC-SA 4.0**, read from the `LICENSE.txt` in each download: attribution, **non-commercial use only**, share-alike |
| **PubMed** (`eutils.ncbi.nlm.nih.gov`) | For each linked study: year, publication type, MeSH geographic terms (study location), author affiliations (research team) | NCBI E-utilities `efetch`, 200 studies per request, cached in `data/cache/` | NLM terms; credit "Courtesy of the U.S. National Library of Medicine" |
| **Natural Earth** (bundled) | Country boundaries for the map | `data/geo/countries.geojson` | Public domain |
| **ChEMBL** (`www.ebi.ac.uk/chembl`) | Standardised identifier, synonyms, brand names, mechanism of action | REST API, at search time | **CC BY-SA 3.0** |
| **Europe PMC** (`www.ebi.ac.uk/europepmc`) | Publications, preprints, open-access status | REST API, at search time | Europe PMC terms; per-article licences recorded |
| **ClinicalTrials.gov** (`clinicaltrials.gov/api/v2`) | Registered studies, site countries, enrolment, reported race/ethnicity, linked result papers | API v2, at search time | ClinicalTrials.gov terms (NLM) |
| **CPIC** (`api.cpicpgx.org`) | Gene–drug pairs, CPIC level, guideline name and URL, guideline PMIDs, data release number | REST API (`pair_view`, `publication`, `guideline`, `change_log`); release number falls back to the latest GitHub release of `cpicpgx/cpic-data` | **CC0**, with attribution requested |

For each download, `data/live/manifest.json` records the URL, the date accessed, the
ClinPGx release date, the CPIC release number, a checksum and the applicable licence.
**Every row keeps its identifiers:** ClinPGx annotation ID, evidence ID, PMID and source
date.

How the pieces join: a ClinPGx *summary annotation* (gene + drug + outcome) lists its
*evidence items*. Each evidence item that is a *variant annotation* has *study
parameters*, which record the cohort size and biogeographical group. The Atlas counts
distinct PMIDs per group. CPIC pairs are matched on drug name + gene symbol.

**Licensing obligations are handled in the app and set out in [ATTRIBUTION.md](ATTRIBUTION.md).**
In short:

- the app shows the attribution and licence on every page;
- every export carries an attribution file;
- the data is **non-commercial only**, and derived data stays under CC BY-NC-SA 4.0;
- anyone you share exports with must first agree to that licence, and ClinPGx can ask
  for proof, so keep a record of who received what;
- the CPIC logo is never used.

ClinPGx asks API users to keep to 2 requests per second (the script makes 2 ClinPGx requests in
total, spaced out) and to contact them before any more-than-trivial use. **Email
feedback@clinpgx.org before hosting the Atlas publicly or scheduling automatic
refreshes.**

## Known limitations

- **PubMed geographic indexing is a proxy for study location, and a sparse one.** NLM
  indexers tag a place only when the paper is about it, so only about 1 in 5 studies has a
  country (October 2026 data). The map therefore shows *at least* where research was
  done, and every view states the share that could be placed. Place tags marked
  "ethnology" describe participants' origin and are kept out of study location.
- **Many studies don't name a specific ancestry group.** About 45% are recorded by ClinPGx
  as "Unknown" or "Multiple groups". These are shown but never counted as a gap.
- **Research-team location is parsed from free-text affiliations.** It is best-effort,
  and unrecognised addresses are left blank rather than guessed.
- **Multi-country studies** count once in each country. Participant totals are not split
  between countries.
- **"Missing" on the map** means no annotated study in this ClinPGx snapshot. In most
  countries that is the honest answer, but it reflects ClinPGx's curation as well as the
  wider literature.

- **Only what ClinPGx has curated.** These are studies ClinPGx curators have annotated,
  not the whole literature. Low numbers can reflect curation coverage as well as real
  research gaps.
- **Biogeographical groups are not ancestry, nationality or identity.** They are ClinPGx's
  standard grouping of study cohorts (Huddart et al., 2019). Studies labelled "Multiple
  groups" or "Unknown" are shown but never counted as a gap.
- **Participant numbers are approximate.** For each study, the Atlas takes the largest
  reported cases + controls and adds them up. It is blank when the study size isn't
  recorded.
- **"Sparse" is a simple rule.** Fewer than 2 studies, or under 200 participants (both
  adjustable in `atlas.py`). This is not a statistical judgement.
- **The file formats may change.** The ClinPGx API is still being finalised. If ClinPGx
  changes its file layout, `ingest.py` stops with a message naming the missing columns
  rather than loading wrong data.
- **CPIC's API address may change.** CPIC may move its API under ClinPGx; set the
  `CPIC_API` environment variable to the new address if it does.

## Roadmap

1. ~~Replace invented records with ClinPGx / CPIC data~~ (done in v0.2; demo data kept as
   a fallback).
2. ~~Traceable PMIDs, source record identifiers and update timestamps~~ (done in v0.2).
3. ~~Separate ancestry, study location and nationality~~ (done in v0.3). Next: recruitment
   site from ClinicalTrials.gov for trials, and self-reported identity where papers give it.
4. ~~Study designs and quality indicators~~ (done in v0.3). Next: outcome definitions and
   an audit of missing study sizes.
5. Benchmark with independent researchers; publish limitations and validation results.
6. Contribution guide, governance and a software licence after IP review. The code
   The data licence (CC BY-NC-SA 4.0) stays separate from whatever code licence is chosen.
   Commercial use of ClinPGx data needs permission from ClinPGx.

## Verification (v0.5)

`python verify.py` checks a downloaded dataset and writes `verification/REPORT.md`. It
checks:

- the download is complete;
- the licence the app shows matches the one in ClinPGx's own `LICENSE.txt`;
- six reference gene–drug pairs (`verification/expected.csv`) give the CPIC level, CPIC
  guideline papers and ClinPGx evidence level documented by CPIC;
- the location and ancestry fields are consistent with each other.

On the ClinPGx 2026-10-05 release (downloaded 2026-10-31), every reference-pair check
passed:

- abacavir/HLA-B, clopidogrel/CYP2C19, warfarin/CYP2C9, fluorouracil/DPYD,
  carbamazepine/HLA-B and allopurinol/HLA-B are all CPIC level A, with the expected
  guideline papers, and all ClinPGx level 1A;
- carbamazepine and allopurinol are most studied in East Asian-ancestry cohorts, as the
  literature on HLA-B\*15:02 and HLA-B\*58:01 leads you to expect.

The checks found and fixed four problems:

- the ClinPGx licence is CC BY-NC-SA 4.0, not CC BY-SA 4.0;
- descriptive text in ClinPGx's population field was being split into fake ancestry
  groups (about 23% of rows);
- PubMed country tags marked "ethnology" (which describe participants' origin) were being
  counted as study locations;
- the CPIC release number was missing.

The report in `verification/` is the one from that run. Rerun `python verify.py` after
every download.

## Status

Prototype for local research demonstration. Not publicly hosted. Checked against
reference facts as described above; it is not a scientific validation of research gaps.
