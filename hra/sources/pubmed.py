"""PubMed via NCBI E-utilities: esearch for counts and IDs, efetch for records."""
from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET

import geo
from .. import queries
from ..http import SourceError
from ..models import FAILED, OK, Licence, Record, SourceResult

EUTILS = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
LICENCE = Licence('NLM terms and conditions', 'https://www.nlm.nih.gov/databases/download/terms_and_conditions.html',
                  'Courtesy of the U.S. National Library of Medicine. Abstracts may be under '
                  'publisher copyright: used for local processing only, never republished in full.')
REG = re.compile(r'(?:registration|registered|clinicaltrials\.gov|identifier)[^.]{0,80}?\b(NCT\d{8})\b', re.I)


def _params(**kw):
    p = {'db': 'pubmed', 'tool': 'HumanResponseAtlas', **kw}
    if os.environ.get('NCBI_EMAIL'):
        p['email'] = os.environ['NCBI_EMAIL']
    if os.environ.get('NCBI_API_KEY'):
        p['api_key'] = os.environ['NCBI_API_KEY']
    return p


def _t(el) -> str:
    return ''.join(el.itertext()).strip() if el is not None else ''


def parse_articles(xml_bytes: bytes) -> dict[str, dict]:
    out = {}
    for art in ET.fromstring(xml_bytes).iter('PubmedArticle'):
        cit = art.find('MedlineCitation')
        pmid = _t(cit.find('PMID'))
        a = cit.find('Article')
        ids = {i.get('IdType'): _t(i) for i in art.iter('ArticleId')}
        year = (_t(a.find('Journal/JournalIssue/PubDate/Year'))
                or _t(a.find('Journal/JournalIssue/PubDate/MedlineDate'))[:4])
        abstract = ' '.join(_t(x) for x in a.iter('AbstractText'))
        ncts = set()
        for db in cit.iter('DataBank'):
            if 'clinicaltrials' in _t(db.find('DataBankName')).lower():
                ncts |= {_t(n) for n in db.iter('AccessionNumber')}
        # registration numbers stated as this study's own (e.g. "Trial registration: NCT...")
        ncts |= {m.group(1) for m in REG.finditer(abstract)}
        places, origins = [], []
        for h in cit.iter('MeshHeading'):
            d = h.find('DescriptorName')
            iso, region = geo.mesh_to_country(_t(d))
            if not (iso or region):
                continue
            quals = {_t(q).lower() for q in h.findall('QualifierName')}
            (origins if 'ethnology' in quals else places).append(iso or region)
        affs = sorted({c for c in (geo.affiliation_country(_t(x)) for x in cit.iter('Affiliation')) if c})
        out[pmid] = {
            'title': _t(a.find('ArticleTitle')), 'year': int(year) if year.isdigit() else None,
            'doi': ids.get('doi', '').lower(), 'pmcid': ids.get('pmc', ''),
            'publication_types': sorted({_t(p) for p in cit.iter('PublicationType')}),
            'abstract': abstract, 'nct_ids': sorted(ncts),
            'mesh_places': sorted(set(places)), 'mesh_origins': sorted(set(origins)),
            'affiliation_countries': affs,
        }
    return out


def search(names: list[str], http, max_per_category: int = 5000) -> SourceResult:
    res = SourceResult('pubmed', OK, licence=LICENCE)
    by_pmid: dict[str, set[str]] = {}
    try:
        for cat, q in queries.pubmed(names).items():
            raw = http.get(f'{EUTILS}/esearch.fcgi',
                           data=_params(term=q, retmax=min(max_per_category, 9999), retmode='json',
                                        sort='relevance'))
            r = json.loads(raw.decode('utf-8')).get('esearchresult')
            if r is None or 'ERROR' in r:
                raise SourceError(f'PubMed rejected the {cat} query: {(r or {}).get("ERROR", "no result")}')
            ids = r.get('idlist', [])
            res.queries.append({'category': cat, 'query': q, 'total': int(r.get('count', 0)),
                                'retrieved': len(ids),
                                'translation': r.get('querytranslation', '')})
            for i in ids:
                by_pmid.setdefault(i, set()).add(cat)
        pmids = sorted(by_pmid, key=int)
        for i in range(0, len(pmids), 200):
            batch = pmids[i:i + 200]
            xml = http.get(f'{EUTILS}/efetch.fcgi', data=_params(id=','.join(batch), retmode='xml'),
                           accept='application/xml')
            for pmid, a in parse_articles(xml).items():
                res.records.append(Record(
                    source='pubmed', source_id=pmid, url=f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/',
                    kind='publication', title=a['title'], year=a['year'], pmid=pmid,
                    pmcid=a['pmcid'], doi=a['doi'], nct_ids=a['nct_ids'],
                    publication_types=a['publication_types'], categories=sorted(by_pmid[pmid]),
                    abstract=a['abstract'],
                    extra={k: a[k] for k in ('mesh_places', 'mesh_origins', 'affiliation_countries')}))
    except SourceError as e:
        res.status, res.error = FAILED, str(e)
    return res
