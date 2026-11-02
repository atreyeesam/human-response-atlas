"""Synthetic test fixtures in the ClinPGx / CPIC file formats.

Every value here is INVENTED for software testing. The column layouts copy the
real ClinPGx bulk-download and CPIC API formats; the contents do not describe
real evidence.
"""
import io
import json
import zipfile

SUMMARY_ANNOTATIONS = (
    "Summary Annotation ID\tVariant/Haplotypes\tGene\tLevel of Evidence\tLevel Override\t"
    "Level Modifiers\tScore\tPhenotype Category\tPMID Count\tEvidence Count\tDrug(s)\t"
    "Phenotype(s)\tLatest History Date (YYYY-MM-DD)\tURL\tSpecialty Population\n"
    "900001\trsFIX1\tGENEA\t1A\t\t\t100\tToxicity\t3\t3\tdrugx\tFixture rash\t2026-01-10\t"
    "https://www.pharmgkb.org/clinicalAnnotation/900001\t\n"
    "900002\trsFIX2\tGENEA\t3\t\t\t2\tEfficacy\t1\t1\tdrugx;drugy\tFixture response\t2025-05-01\t"
    "https://www.pharmgkb.org/clinicalAnnotation/900002\t\n"
)
SUMMARY_EVIDENCE = (
    "Summary Annotation ID\tEvidence ID\tEvidence Type\tEvidence URL\tPMID\tSummary\tScore\n"
    "900001\t800001\tVariant Drug Annotation\thttps://www.pharmgkb.org/variantAnnotation/800001\t11111\tFIXTURE\t2\n"
    "900001\t800002\tVariant Drug Annotation\thttps://www.pharmgkb.org/variantAnnotation/800002\t22222\tFIXTURE\t2\n"
    "900001\t800003\tVariant Phenotype Annotation\thttps://www.pharmgkb.org/variantAnnotation/800003\t33333\tFIXTURE\t1\n"
    "900001\t700001\tGuideline Annotation\thttps://www.pharmgkb.org/guidelineAnnotation/700001\t\tFIXTURE\t\n"
    "900002\t800004\tVariant Drug Annotation\thttps://www.pharmgkb.org/variantAnnotation/800004\t44444\tFIXTURE\t1\n"
)
LICENSE_TEXT = ("This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike "
                "4.0 International license.\nTo view a copy of this license, visit "
                "http://creativecommons.org/licenses/by-nc-sa/4.0/ (FIXTURE COPY)\n")
STUDY_PARAMETERS = (
    "Study Parameters ID\tVariant Annotation ID\tStudy Type\tStudy Cases\tStudy Controls\t"
    "Characteristics\tCharacteristics Type\tFrequency In Cases\tAllele Of Frequency In Cases\t"
    "Frequency In Controls\tAllele Of Frequency In Controls\tP Value\tRatio Stat Type\t"
    "Ratio Stat\tConfidence Interval Start\tConfidence Interval Stop\tBiogeographical Groups\n"
    # PMID 11111: European cohort, annotated twice (same cohort, must not double count)
    "1\t800001\tcase/control\t300\t700\t\t\t\t\t\t\t\t\t\t\t\tEuropean\n"
    "2\t800001\tcase/control\t300\t700\t\t\t\t\t\t\t\t\t\t\t\tEuropean\n"
    # PMID 22222: East Asian, small cohort
    "3\t800002\tcohort\t50\t\t\t\t\t\t\t\t\t\t\t\t\tEast Asian\n"
    # PMID 33333: European, size not reported
    "4\t800003\tcohort\t\t\t\t\t\t\t\t\t\t\t\t\t\tEuropean\n"
    # PMID 44444: Sub-Saharan African
    "5\t800004\tcohort\t120\t80\t\t\t\t\t\t\t\t\t\t\t\t\"Sub-Saharan African, 87.8% Yoruba, 12.2% other\"\n"
    # unrelated annotation not linked to any summary annotation
    "6\t899999\tcohort\t10\t10\t\t\t\t\t\t\t\t\t\t\t\tUnknown\n"
)
VAR_DRUG_ANN = (
    "Variant Annotation ID\tVariant/Haplotypes\tGene\tDrug(s)\tPMID\tPhenotype Category\tSignificance\n"
    "800001\trsFIX1\tGENEA\tdrugx\t11111\tToxicity\tyes\n"
    "800002\trsFIX1\tGENEA\tdrugx\t22222\tToxicity\tno\n"
    "800004\trsFIX2\tGENEA\tdrugy\t44444\tEfficacy\tnot stated\n"
)
VAR_PHENO_ANN = (
    "Variant Annotation ID\tVariant/Haplotypes\tGene\tDrug(s)\tPMID\tPhenotype Category\tSignificance\n"
    "800003\trsFIX1\tGENEA\tdrugx\t33333\tToxicity\tyes\n"
)

# PubMed records. Note the deliberate mismatches between ancestry and location:
# PMID 22222 is an East Asian-ancestry cohort indexed as studied in the United States.
PUBMED = {
    "11111": dict(year="2019", types=["Journal Article", "Multicenter Study"],
                  mesh=["Humans", "Germany", "European Continental Ancestry Group"],
                  aff=["Dept Pharmacology, Fixture University, Berlin, Germany."]),
    "22222": dict(year="2021", types=["Journal Article", "Randomized Controlled Trial"],
                  mesh=["Humans", "California", "Asian People", "Korea/ethnology"],
                  aff=["Fixture Institute, Seoul 03080, Republic of Korea.",
                       "Fixture Hospital, Los Angeles, CA 90095, USA."]),
    "33333": dict(year="2012", types=["Journal Article"], mesh=None,   # not yet MeSH-indexed
                  aff=["Fixture Lab, Lyon, France"]),
    "44444": dict(year="2024", types=["Journal Article", "Observational Study"],
                  mesh=["Humans", "Nigeria", "Africa South of the Sahara"],
                  aff=["Fixture College of Medicine, Ibadan, Nigeria",
                       "Fixture Centre, London, UK"]),
}


def pubmed_xml(ids) -> bytes:
    arts = []
    for pmid in ids:
        r = PUBMED.get(pmid)
        if r is None:
            continue
        def heading(m):
            name, _, qual = m.partition("/")
            q = f"<QualifierName UI='Q0'>{qual}</QualifierName>" if qual else ""
            return f"<MeshHeading><DescriptorName UI='D0'>{name}</DescriptorName>{q}</MeshHeading>"
        mesh = ("" if r["mesh"] is None else "<MeshHeadingList>" + "".join(
            heading(m) for m in r["mesh"]) + "</MeshHeadingList>")
        affs = "".join(f"<Author><AffiliationInfo><Affiliation>{a}</Affiliation></AffiliationInfo></Author>"
                       for a in r["aff"])
        types = "".join(f"<PublicationType>{t}</PublicationType>" for t in r["types"])
        arts.append(
            f"<PubmedArticle><MedlineCitation><PMID>{pmid}</PMID><Article>"
            f"<Journal><JournalIssue><PubDate><Year>{r['year']}</Year></PubDate></JournalIssue>"
            f"<ISOAbbreviation>Fixture J</ISOAbbreviation></Journal>"
            f"<ArticleTitle>FIXTURE article {pmid}</ArticleTitle><AuthorList>{affs}</AuthorList>"
            f"<PublicationTypeList>{types}</PublicationTypeList></Article>{mesh}"
            f"</MedlineCitation></PubmedArticle>")
    return ("<?xml version='1.0'?><PubmedArticleSet>" + "".join(arts) + "</PubmedArticleSet>").encode()

CPIC_PAIRS = [
    {"pairid": 1, "drugid": "RxNorm:1", "drugname": "drugx", "genesymbol": "GENEA",
     "guidelinename": "GENEA and Drugx (FIXTURE)", "guidelineurl": "https://example.org/g1",
     "cpiclevel": "A", "clinpgxlevel": "1A", "pgxtesting": "Testing required",
     "pmids": ["99999"], "usedforrecommendation": "Yes", "provisional": False},
]
CPIC_PUBLICATIONS = [
    {"guidelineid": 10, "pmid": "99999", "pmcid": None, "doi": "10.0000/fixture",
     "title": "Fixture guideline", "year": 2024, "journal": "Fixture J", "url": None},
]
CPIC_GUIDELINES = [{"id": 10, "name": "GENEA and Drugx (FIXTURE)",
                    "url": "https://example.org/g1", "clinpgxid": "PA000"}]
CPIC_CHANGE_LOG = [{"date": "2026-09-01", "deployedrelease": "v9.9.9"}]


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


def fake_get(url: str, accept: str = "*/*", retries: int = 3, data: bytes | None = None) -> bytes:
    if "efetch.fcgi" in url:
        from urllib.parse import parse_qs
        ids = parse_qs(data.decode())["id"][0].split(",")
        return pubmed_xml(ids)
    if url.endswith("summaryAnnotations.zip"):
        return _zip({"summary_annotations.tsv": SUMMARY_ANNOTATIONS,
                     "summary_ann_evidence.tsv": SUMMARY_EVIDENCE,
                     "CREATED_2026-10-01.txt": "",
                     "LICENSE.txt": LICENSE_TEXT})
    if url.endswith("variantAnnotations.zip"):
        return _zip({"study_parameters.tsv": STUDY_PARAMETERS,
                     "var_drug_ann.tsv": VAR_DRUG_ANN,
                     "var_pheno_ann.tsv": VAR_PHENO_ANN,
                     "CREATED_2026-10-01.txt": ""})
    if "/pair_view" in url:
        return json.dumps(CPIC_PAIRS).encode()
    if "/publication" in url:
        return json.dumps(CPIC_PUBLICATIONS).encode()
    if "/guideline" in url:
        return json.dumps(CPIC_GUIDELINES).encode()
    if "/change_log" in url:
        return json.dumps(CPIC_CHANGE_LOG).encode()
    raise AssertionError(f"unexpected URL in test: {url}")
