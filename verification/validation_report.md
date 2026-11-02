# Validation report (v0.7)

13 of 13 checks passed (live run).

| Medicine | Check | Expected | Result | Detail | Source of truth |
|---|---|---|---|---|---|
| clopidogrel | gene_established | CYP2C19 | PASS | established: CYP2C19 | CPIC guideline (cpic-data repository; PMID 35034351) |
| clopidogrel | trade_name_resolves | Plavix | PASS | trade names: Clopidogrel 1a pharma, Clopidogrel 1a-pharma, Clopidogrel acino, Clopidogrel acino pharma, Clopidogrel acino pharma gmbh, Clopidogrel apotex, Clopidogrel bgr (previously zylagren), Clopidogrel bisulfate | Common brand name for clopidogrel |
| clopidogrel | landmark_pmid_found | 19106084 | PASS | 8,828 PMIDs retrieved (pubmed 8,801/10,938; europepmc 4,138/4,421) | Mega JL et al. Cytochrome P-450 polymorphisms and response to clopidogrel. NEJM 2009 (PubMed listing) |
| clopidogrel | landmark_trial_found | NCT01742117 | PASS | 1,454 trial IDs retrieved | TAILOR-PCI trial registration (ClinicalTrials.gov listing) |
| clopidogrel | curated_ancestry_includes | East Asian | PASS | East Asian: 58 studies | ClinPGx curated study parameters (verified 2026-10-31) |
| warfarin | gene_established | CYP2C9;VKORC1 | PASS | established: CYP2C9, CYP4F2, VKORC1 | CPIC warfarin guideline (PMIDs 21900891; 28198005) |
| warfarin | landmark_pmid_found | 19228618 | PASS | 31,095 PMIDs retrieved (pubmed 26,849/85,803 TRUNCATED; europepmc 18,992/31,558 TRUNCATED) | IWPC. Estimation of the warfarin dose with clinical and pharmacogenetic data. NEJM 2009 (PubMed listing) |
| bisoprolol | no_gene_established |  | PASS | established: none | No CPIC level A/B pair for bisoprolol in CPIC data (2026-10-31) |
| bisoprolol | landmark_pmid_found | 10023943 | PASS | 791 PMIDs retrieved (pubmed 790/942; europepmc 457/467) | CIBIS-II. Lancet 1999 (PubMed listing) |
| bisoprolol | efficacy_not_limited |  | PASS | efficacy: Established evidence | Bisoprolol has many randomised trials and meta-analyses (e.g. CIBIS-II) |
| fluorouracil | gene_established | DPYD | PASS | established: DPYD | CPIC fluoropyrimidines guideline (PMIDs 23988873; 29152729) |
| fluorouracil | landmark_pmid_found | 30348537 | PASS | 13,956 PMIDs retrieved (pubmed 13,892/22,866 TRUNCATED; europepmc 5,330/5,452) | Henricks LM et al. DPYD genotype-guided dose individualisation. Lancet Oncol 2018 (PubMed listing) |
| tamoxifen | gene_established | CYP2D6 | PASS | established: CYP2D6 | CPIC tamoxifen/CYP2D6 guideline level A in CPIC data (2026-10-31) |

## Source status

| Medicine | Source | Status | Records | Error |
|---|---|---|---|---|
| clopidogrel | chembl | searched | 0 |  |
| clopidogrel | clinpgx | searched | 215 |  |
| clopidogrel | cpic | searched | 0 |  |
| clopidogrel | pubmed | searched | 8801 |  |
| clopidogrel | europepmc | searched | 4138 |  |
| clopidogrel | clinicaltrials | searched | 1291 |  |
| warfarin | chembl | searched | 0 |  |
| warfarin | clinpgx | searched | 274 |  |
| warfarin | cpic | searched | 0 |  |
| warfarin | pubmed | searched | 26849 |  |
| warfarin | europepmc | searched | 18992 |  |
| warfarin | clinicaltrials | searched | 5000 |  |
| bisoprolol | chembl | searched | 0 |  |
| bisoprolol | clinpgx | searched | 1 |  |
| bisoprolol | cpic | searched | 0 |  |
| bisoprolol | pubmed | searched | 790 |  |
| bisoprolol | europepmc | searched | 457 |  |
| bisoprolol | clinicaltrials | searched | 143 |  |
| fluorouracil | chembl | searched | 0 |  |
| fluorouracil | clinpgx | searched | 182 |  |
| fluorouracil | cpic | searched | 0 |  |
| fluorouracil | pubmed | searched | 13892 |  |
| fluorouracil | europepmc | searched | 5330 |  |
| fluorouracil | clinicaltrials | searched | 5000 |  |
| tamoxifen | chembl | searched | 0 |  |
| tamoxifen | clinpgx | searched | 80 |  |
| tamoxifen | cpic | searched | 0 |  |
| tamoxifen | pubmed | searched | 8256 |  |
| tamoxifen | europepmc | searched | 3191 |  |
| tamoxifen | clinicaltrials | searched | 686 |  |
