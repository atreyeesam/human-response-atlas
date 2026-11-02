"""Fake responses in each source's documented format. All content is INVENTED for tests."""
import json
from urllib.parse import parse_qs, urlparse

CHEMBL_PARENT = {"molecule_chembl_id": "CHEMBL1771", "pref_name": "CLOPIDOGREL", "max_phase": 4,
                 "molecule_hierarchy": {"parent_chembl_id": "CHEMBL1771"},
                 "molecule_synonyms": [{"molecule_synonym": "Clopidogrel", "syn_type": "INN"},
                                       {"molecule_synonym": "SR-25990C", "syn_type": "RESEARCH_CODE"}]}
CHEMBL_SALT = {"molecule_chembl_id": "CHEMBL1200", "pref_name": "CLOPIDOGREL BISULFATE", "max_phase": 4,
               "molecule_hierarchy": {"parent_chembl_id": "CHEMBL1771"},
               "molecule_synonyms": [{"molecule_synonym": "Clopidogrel bisulfate", "syn_type": "USAN"},
                                     {"molecule_synonym": "Plavix", "syn_type": "TRADE_NAME"}]}
CHEMBL_DECOY = {"molecule_chembl_id": "CHEMBL9999", "pref_name": "CLOPIDOGREL ANALOGUE X", "max_phase": 0,
                "molecule_hierarchy": {"parent_chembl_id": "CHEMBL9999"}, "molecule_synonyms": []}
CHEMBL_SEARCH = {"page_meta": {"total_count": 3}, "molecules": [CHEMBL_DECOY, CHEMBL_SALT, CHEMBL_PARENT]}
CHEMBL_MECH = {"mechanisms": [{"mechanism_of_action": "P2Y12 receptor antagonist",
                               "target_chembl_id": "CHEMBL2001", "action_type": "ANTAGONIST"}]}

ESEARCH = {"pgx": ["100", "101"], "efficacy": ["101", "102", "103"], "safety": ["103"]}
ARTICLES = {
    "100": dict(title="CYP2C19 genotype and clopidogrel response in a fixture cohort", year="2015",
                doi="10.1000/FIX.100", types=["Journal Article"], databank=["NCT00000001"],
                abstract="We genotyped 1,200 Bangladeshi patients recruited in Dhaka, Bangladesh. "
                         "Carriers had higher risk (hazard ratio 1.80, 95% CI 1.20-2.70).",
                mesh=["Bangladesh"], aff=["Fixture University, Dhaka, Bangladesh."]),
    "101": dict(title="A randomised fixture trial of clopidogrel versus placebo in adults", year="2018",
                doi="", types=["Journal Article", "Randomized Controlled Trial"], databank=[],
                abstract="A total of 4,000 participants were randomised.", mesh=[], aff=["Fixture Inst, London, UK"]),
    "102": dict(title="Clopidogrel efficacy: a fixture meta-analysis of randomised trials", year="2020",
                doi="10.1000/fix.102", types=["Journal Article", "Meta-Analysis"], databank=[],
                abstract="Twelve trials were pooled.", mesh=[], aff=[]),
    "103": dict(title="Adverse events with clopidogrel in a fixture registry", year="2021",
                doi="", types=["Journal Article", "Randomized Controlled Trial"], databank=[],
                abstract="Among 310 Han Chinese patients enrolled in Shanghai, China, bleeding occurred.",
                mesh=["China/ethnology"], aff=["Fixture Hospital, Shanghai, China"]),
}
EPMC = [
    {"id": "100", "source": "MED", "pmid": "100", "doi": "10.1000/fix.100", "title": ARTICLES["100"]["title"],
     "pubYear": "2015", "isOpenAccess": "N", "abstractText": ARTICLES["100"]["abstract"]},
    {"id": "PPR1", "source": "PPR", "doi": "10.1101/fix.pre", "pubYear": "2018",
     "title": "A randomised fixture trial of clopidogrel versus placebo in adults.", "isOpenAccess": "Y",
     "license": "cc by"},
    {"id": "200", "source": "MED", "pmid": "", "doi": "10.1000/fix.200", "pubYear": "2022",
     "title": "Clopidogrel response in a fixture Nigerian cohort study", "isOpenAccess": "Y",
     "license": "cc by", "abstractText": "We studied 85 Nigerian patients in Ibadan, Nigeria."},
]
TRIALS = [
    {"protocolSection": {"identificationModule": {"nctId": "NCT00000001", "briefTitle": "Fixture genotype trial"},
                         "statusModule": {"overallStatus": "COMPLETED", "startDateStruct": {"date": "2013-02"}},
                         "designModule": {"studyType": "INTERVENTIONAL", "phases": ["PHASE4"],
                                          "enrollmentInfo": {"count": 1200}},
                         "contactsLocationsModule": {"locations": [{"country": "Bangladesh"}, {"country": "India"}]}},
     "hasResults": True,
     "resultsSection": {"baselineCharacteristicsModule": {
         "groups": [{"id": "BG000", "title": "Arm A"}, {"id": "BG001", "title": "Total"}],
         "measures": [{"title": "Race (NIH/OMB)", "classes": [{"categories": [
             {"title": "Asian", "measurements": [{"groupId": "BG000", "value": "600"}, {"groupId": "BG001", "value": "1150"}]},
             {"title": "White", "measurements": [{"groupId": "BG000", "value": "20"}, {"groupId": "BG001", "value": "50"}]}]}]}]}}},
    {"protocolSection": {"identificationModule": {"nctId": "NCT00000002", "briefTitle": "Fixture safety registry"},
                         "statusModule": {"overallStatus": "COMPLETED", "startDateStruct": {"date": "2019"}},
                         "designModule": {"studyType": "OBSERVATIONAL", "enrollmentInfo": {"count": 310}},
                         "contactsLocationsModule": {"locations": [{"country": "China"}]},
                         "referencesModule": {"references": [{"pmid": "103", "type": "RESULT"},
                                                             {"pmid": "102", "type": "BACKGROUND"}]}}},
]


def efetch_xml(ids):
    arts = []
    for i in ids:
        a = ARTICLES[i]
        def heading(m):
            n, _, q = m.partition("/")
            return f"<MeshHeading><DescriptorName>{n}</DescriptorName>" + (f"<QualifierName>{q}</QualifierName>" if q else "") + "</MeshHeading>"
        mesh = "<MeshHeadingList>" + "".join(heading(m) for m in a["mesh"]) + "</MeshHeadingList>" if a["mesh"] else ""
        db = ("<DataBankList><DataBank><DataBankName>ClinicalTrials.gov</DataBankName><AccessionNumberList>"
              + "".join(f"<AccessionNumber>{n}</AccessionNumber>" for n in a["databank"])
              + "</AccessionNumberList></DataBank></DataBankList>") if a["databank"] else ""
        arts.append(
            f"<PubmedArticle><MedlineCitation><PMID>{i}</PMID><Article><Journal><JournalIssue><PubDate><Year>{a['year']}</Year></PubDate></JournalIssue></Journal>"
            f"<ArticleTitle>{a['title']}</ArticleTitle><Abstract><AbstractText>{a['abstract']}</AbstractText></Abstract>"
            f"<AuthorList>{''.join(f'<Author><AffiliationInfo><Affiliation>{x}</Affiliation></AffiliationInfo></Author>' for x in a['aff'])}</AuthorList>"
            f"<PublicationTypeList>{''.join(f'<PublicationType>{t}</PublicationType>' for t in a['types'])}</PublicationTypeList>{db}</Article>{mesh}</MedlineCitation>"
            f"<PubmedData><ArticleIdList><ArticleId IdType='pubmed'>{i}</ArticleId>"
            + (f"<ArticleId IdType='doi'>{a['doi']}</ArticleId>" if a['doi'] else "")
            + "</ArticleIdList></PubmedData></PubmedArticle>")
    return ("<PubmedArticleSet>" + "".join(arts) + "</PubmedArticleSet>").encode()


class FakeInternet:
    """Transport for hra.http.Http. Set `down` to a set of hosts to simulate outages."""
    def __init__(self, down=(), epmc_error=False):
        self.down, self.epmc_error, self.calls = set(down), epmc_error, []

    def __call__(self, url, data, headers):
        import urllib.error
        u = urlparse(url)
        self.calls.append(u.hostname)
        if u.hostname in self.down:
            raise urllib.error.URLError('simulated outage')
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        form = {k: v[0] for k, v in parse_qs(data.decode()).items()} if data else {}
        if 'chembl' in u.path and u.path.endswith('/molecule/CHEMBL1771.json'):
            return json.dumps(CHEMBL_PARENT).encode()
        if 'chembl' in u.path and u.path.endswith('/molecule.json'):
            fam = [CHEMBL_PARENT, CHEMBL_SALT] if q.get('molecule_hierarchy__parent_chembl_id') == 'CHEMBL1771' else []
            return json.dumps({"page_meta": {"total_count": len(fam)}, "molecules": fam}).encode()
        if 'chembl' in u.path and 'molecule/search' in u.path:
            return json.dumps(CHEMBL_SEARCH if q.get('q', '').lower() in ('clopidogrel', 'plavix') else
                              {"page_meta": {"total_count": 0}, "molecules": []}).encode()
        if 'chembl' in u.path and 'mechanism' in u.path:
            return json.dumps(CHEMBL_MECH).encode()
        if u.path.endswith('esearch.fcgi'):
            term = form['term']
            cat = 'pgx' if 'pharmacogen' in term else 'efficacy' if 'randomized' in term else 'safety'
            ids = ESEARCH[cat] if ('clopidogrel' in term or 'plavix' in term) else []
            return json.dumps({"esearchresult": {"count": str(len(ids) + (500 if cat == 'pgx' and ids else 0)),
                                                 "idlist": ids, "querytranslation": term}}).encode()
        if u.path.endswith('efetch.fcgi'):
            return efetch_xml(form['id'].split(','))
        if 'europepmc' in u.path:
            if self.epmc_error:
                return json.dumps({"errCode": 404, "errMsg": "simulated bad request"}).encode()
            hits = EPMC if 'clopidogrel' in q['query'] else []
            if q.get('cursorMark') != '*':
                hits = []
            return json.dumps({"hitCount": len(EPMC) if 'clopidogrel' in q['query'] else 0,
                               "nextCursorMark": "END", "resultList": {"result": hits}}).encode()
        if 'clinicaltrials' in (u.hostname or ''):
            hits = TRIALS if 'clopidogrel' in q.get('query.intr', '').lower() else []
            return json.dumps({"totalCount": len(hits), "studies": hits}).encode()
        raise AssertionError(f'unexpected request {url}')
