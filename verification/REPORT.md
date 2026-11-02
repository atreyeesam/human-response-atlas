# Human Response Atlas — verification report

Generated 2026-10-31 09:53 UTC from `/home/claude/realdata/data/live`. ClinPGx release 2026-10-05 · CPIC release not stated; downloaded 2026-10-31T09:42:20+00:00.

**48 checks passed, 2 failed.**

## Checks

| area | check | result | detail |
|---|---|---|---|
| Ingest | ClinPGx summaryAnnotations downloaded from api.clinpgx.org | PASS | 1,236,737 bytes; release 2026-10-05; sha256 16e10905ca67… |
| Ingest | ClinPGx summaryAnnotations release date recorded | PASS | 2026-10-05 |
| Ingest | ClinPGx variantAnnotations downloaded from api.clinpgx.org | PASS | 4,296,635 bytes; release 2026-10-05; sha256 ab29a58fbdad… |
| Ingest | ClinPGx variantAnnotations release date recorded | PASS | 2026-10-05 |
| Ingest | CPIC pairs downloaded | PASS | 574 pairs; release None |
| Ingest | CPIC release number recorded | FAIL | None |
| Ingest | PubMed look-ups completed without error | PASS | 5,955 PMIDs; 1 not found |
| Ingest | associations.csv has rows | PASS | 6,913 rows |
| Ingest | evidence.csv has rows | PASS | 15,542 rows |
| Ingest | study_populations.csv has rows | PASS | 19,457 rows |
| Ingest | pubmed.csv has rows | PASS | 5,955 rows |
| Ingest | study_locations.csv has rows | PASS | 8,104 rows |
| Ingest | cpic_pairs.csv has rows | PASS | 574 rows |
| Ingest | Evidence rows link to summary annotations | PASS | 98.1% linked (the rest belong to annotations with no drug or gene listed) |
| Ingest | Variant evidence links to study parameters | PASS | 97.5% of variant-annotation evidence has study parameters |
| Ingest | Variant evidence carries PMIDs | PASS | 100.0% |
| Ingest | Annotation dates parse and are not in the future | PASS | 2021-03-24 to 2026-09-08 |
| Ingest | Every ancestry value is a recognised ClinPGx group | PASS | 12 labels, all recognised |
| Ingest | All 9 ClinPGx biogeographical groups present | PASS | also present: In vitro (no participants), Multiple groups, Unknown |
| Licences | Licence/readme files shipped inside ClinPGx downloads were saved | PASS | clinpgx_summaryAnnotations_LICENSE.txt, clinpgx_variantAnnotations_LICENSE.txt |
| Licences | ClinPGx licence file names a Creative Commons licence | PASS | Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0) |
| Licences | App and exports show the licence named in that file | PASS | app shows CC BY-NC-SA 4.0 |
| Licences | NonCommercial restriction | NOTE | ClinPGx data may not be used for commercial purposes; the app footer, About tab and every export say so. |
| Licences | Export attribution names the licence, NC and share-alike terms | PASS |  |
| Licences | Excerpt of clinpgx_summaryAnnotations_LICENSE.txt | NOTE | This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International license. To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/ or send a letter to Creative Commons, PO Box 1866, Mountain View, CA 94042, USA. Some requirements … |
| Licences | Excerpt of clinpgx_variantAnnotations_LICENSE.txt | NOTE | This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International license. To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/ or send a letter to Creative Commons, PO Box 1866, Mountain View, CA 94042, USA. Some requirements … |
| Licences | cpic licence recorded in manifest | PASS | CC0 1.0 Universal (public domain dedication), with CPIC attribution requests |
| Licences | pubmed licence recorded in manifest | PASS | NLM terms and conditions (bibliographic data courtesy of the U.S. National Library of Medicine) |
| Licences | Natural Earth map is public domain | PASS | bundled licence file |
| Reference pairs | abacavir / HLA-B: CPIC level = A | PASS | found A |
| Reference pairs | abacavir / HLA-B: CPIC guideline PMIDs include 22378157, 24561393 | PASS | found 22378157, 24561393 |
| Reference pairs | abacavir / HLA-B: top ClinPGx level = 1A | PASS | found 1A (1 annotations) |
| Reference pairs | clopidogrel / CYP2C19: CPIC level = A | PASS | found A |
| Reference pairs | clopidogrel / CYP2C19: CPIC guideline PMIDs include 21716271, 23698643, 35034351 | PASS | found 21716271, 23698643, 35034351 |
| Reference pairs | clopidogrel / CYP2C19: top ClinPGx level = 1A | PASS | found 1A (6 annotations) |
| Reference pairs | warfarin / CYP2C9: CPIC level = A | PASS | found A |
| Reference pairs | warfarin / CYP2C9: CPIC guideline PMIDs include 21900891, 28198005 | PASS | found 21900891, 28198005 |
| Reference pairs | warfarin / CYP2C9: top ClinPGx level = 1A | PASS | found 1A (14 annotations) |
| Reference pairs | fluorouracil / DPYD: CPIC level = A | PASS | found A |
| Reference pairs | fluorouracil / DPYD: CPIC guideline PMIDs include 23988873, 29152729 | PASS | found 23988873, 29152729 |
| Reference pairs | fluorouracil / DPYD: top ClinPGx level = 1A | PASS | found 1A (64 annotations) |
| Reference pairs | carbamazepine / HLA-B: CPIC level = A | PASS | found A |
| Reference pairs | carbamazepine / HLA-B: CPIC guideline PMIDs include 23695185, 29392710 | PASS | found 23695185, 29392710 |
| Reference pairs | carbamazepine / HLA-B: top ClinPGx level = 1A | PASS | found 1A (8 annotations) |
| Reference pairs | carbamazepine / HLA-B: most-studied ancestry = East Asian | PASS | found East Asian |
| Reference pairs | allopurinol / HLA-B: CPIC level = A | PASS | found A |
| Reference pairs | allopurinol / HLA-B: CPIC guideline PMIDs include 23232549, 26094938 | PASS | found 23232549, 26094938 |
| Reference pairs | allopurinol / HLA-B: top ClinPGx level = 1A | PASS | found 1A (2 annotations) |
| Reference pairs | allopurinol / HLA-B: most-studied ancestry = East Asian | PASS | found East Asian |
| Coverage | Studies with recorded ancestry | NOTE | 3,234 of 5,908 (55%) |
| Coverage | Studies with a country-level study location (PubMed MeSH) | NOTE | 1,272 (22%); 209 not yet indexed; 31 region only |
| Coverage | Studies with a recognised research-team country | NOTE | 5,577 (94%) |
| Coverage | PubMed data separates “ethnology” tags from study location | FAIL | downloaded before v0.5: run python ingest.py again, then python verify.py |
| Coverage | Study-location coverage is limited | NOTE | NLM adds geographic MeSH terms only when place is a subject of the paper, so most studies have no indexed country. The app reports this share on every view. |
| Consistency | Indexed study country matches an author country in most studies | PASS | 85% of 1,272 located studies |
| Consistency | Studies located in Japan, China, Korea, Taiwan mostly include East Asian participants | PASS | 99% of 469 studies naming a specific group |
| Consistency | Studies located in Germany, France, Italy, Spain, Netherlands, UK, Sweden, Denmark, Poland mostly include European participants | PASS | 98% of 125 studies naming a specific group |

## Reference gene–drug pairs

| pair | cpic_level | top_clinpgx_level | annotations | studies | most_studied_ancestry | top_study_countries | reference |
|---|---|---|---|---|---|---|---|
| abacavir / HLA-B | A | 1A | 1 | 11 | European | Switzerland (1), Spain (1), Canada (1) | CPIC abacavir/HLA-B guideline 2012 and 2014 update (cpic-data repository; PubMed 24561393) |
| clopidogrel / CYP2C19 | A | 1A | 6 | 154 | East Asian | South Korea (10), China (10), Japan (3) | CPIC clopidogrel/CYP2C19 guideline 2011 2013 and 2022 update (cpic-data repository; PubMed 35034351) |
| warfarin / CYP2C9 | A | 1A | 14 | 175 | East Asian | China (13), South Korea (9), Japan (9) | CPIC warfarin guideline 2011 and 2017 update (cpic-data repository; PubMed 28198005) |
| fluorouracil / DPYD | A | 1A | 64 | 99 | European | South Korea (1), Portugal (1), Poland (1) | CPIC fluoropyrimidines/DPYD guideline 2013 and 2017 update (cpic-data repository; PubMed 29152729) |
| carbamazepine / HLA-B | A | 1A | 8 | 55 | East Asian | China (11), Thailand (6), India (5) | CPIC carbamazepine/HLA guideline 2013 and 2017 update; HLA-B*15:02 evidence comes mainly from East Asian cohorts |
| allopurinol / HLA-B | A | 1A | 2 | 44 | East Asian | South Korea (5), Thailand (4), China (4) | CPIC allopurinol/HLA-B guideline 2013 and 2015 update; HLA-B*58:01 evidence comes mainly from East Asian cohorts |

## Manual spot-check sample

Open each PubMed link and confirm that the MeSH geographic term and author affiliations match the study location and research team shown.

| pmid | year | ancestry | mesh_geo_terms | study_location | research_team | pubmed_url |
|---|---|---|---|---|---|---|
| 22210422 | 2011.0 | East Asian | Japan | Japan | Japan | https://pubmed.ncbi.nlm.nih.gov/22210422/ |
| 20833111 | 2010.0 | East Asian | China | China | China | https://pubmed.ncbi.nlm.nih.gov/20833111/ |
| 23941071 | 2013.0 | East Asian | China | China | China | https://pubmed.ncbi.nlm.nih.gov/23941071/ |
| 15057820 | 2004.0 | East Asian | China | China | Taiwan | https://pubmed.ncbi.nlm.nih.gov/15057820/ |
| 27898234 | 2017.0 | Unknown | Australia;Europe;United States | Australia, United States of America | Australia, Germany, United States of America | https://pubmed.ncbi.nlm.nih.gov/27898234/ |
| 11337943 | 2001.0 | East Asian | Japan | Japan | Japan | https://pubmed.ncbi.nlm.nih.gov/11337943/ |
| 19891552 | 2009.0 | European | Italy | Italy | Italy | https://pubmed.ncbi.nlm.nih.gov/19891552/ |
| 21076384 | 2010.0 | East Asian | Korea | South Korea | South Korea | https://pubmed.ncbi.nlm.nih.gov/21076384/ |
| 26655481 | 2016.0 | East Asian | Republic of Korea | South Korea | South Korea | https://pubmed.ncbi.nlm.nih.gov/26655481/ |
| 20339978 | 2010.0 | Near Eastern | Turkey | Turkey | Turkey | https://pubmed.ncbi.nlm.nih.gov/20339978/ |
| 18424454 | 2008.0 | Near Eastern | Israel | Israel | United States of America | https://pubmed.ncbi.nlm.nih.gov/18424454/ |
| 16691038 | 2006.0 | European | Slovenia | Slovenia | Slovenia | https://pubmed.ncbi.nlm.nih.gov/16691038/ |
