"""PubMed (NCBI E-utilities) enrichment for the PMIDs linked from ClinPGx.

For each PMID we keep only bibliographic metadata and NLM indexing:
publication year, journal, publication types, MeSH geographic descriptors
(where the study was conducted or which place it concerns, as indexed by NLM)
and the countries in author affiliations (where the research team is based).

Results are cached in data/cache/pubmed.json so later refreshes only fetch
new PMIDs (plus older un-indexed ones, which NLM may have indexed since).

NCBI usage rules: at most 3 requests/second without an API key (10 with one),
and identify the tool and a contact email. Set NCBI_EMAIL (recommended) and
optionally NCBI_API_KEY as environment variables.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import geo

EUTILS = os.environ.get('NCBI_EUTILS', 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils').rstrip('/')
CACHE_FILE = Path(__file__).parent / 'data' / 'cache' / 'pubmed.json'
BATCH = 200
REFETCH_UNINDEXED_AFTER = timedelta(days=30)
REFETCH_ALL_AFTER = timedelta(days=365)
# v2 (Atlas v0.5): geographic headings carrying the MeSH qualifier "ethnology" describe
# "the place of origin of a group of people" (NLM scope note), i.e. participants' origin,
# not where the study was done. Records cached under v1 lack this distinction.
SCHEMA = 2


def _text(el) -> str:
    return ''.join(el.itertext()).strip() if el is not None else ''


def parse_efetch(xml_bytes: bytes) -> dict[str, dict]:
    """Parse a PubMed efetch XML batch into {pmid: record}."""
    out = {}
    root = ET.fromstring(xml_bytes)
    for art in root.iter('PubmedArticle'):
        cit = art.find('MedlineCitation')
        if cit is None:
            continue
        pmid = _text(cit.find('PMID'))
        article = cit.find('Article')
        year = ''
        if article is not None:
            year = (_text(article.find('Journal/JournalIssue/PubDate/Year'))
                    or _text(article.find('Journal/JournalIssue/PubDate/MedlineDate'))[:4]
                    or _text(article.find('ArticleDate/Year')))
        pub_types = [_text(p) for p in cit.iter('PublicationType')]
        mesh = cit.find('MeshHeadingList')
        geo_terms, countries, regions, origin_terms = [], [], [], []
        if mesh is not None:
            for heading in mesh.iter('MeshHeading'):
                d = heading.find('DescriptorName')
                if d is None:
                    continue
                name = _text(d)
                quals = {_text(q).lower() for q in heading.findall('QualifierName')}
                iso, region = geo.mesh_to_country(name)
                if not (iso or region):
                    continue
                if 'ethnology' in quals:
                    # place of origin of a group of people -> NOT a study location
                    origin_terms.append(f'{name}/ethnology')
                    continue
                geo_terms.append(name)
                if iso:
                    countries.append(iso)
                else:
                    regions.append(region)
        aff_countries = []
        for aff in cit.iter('Affiliation'):
            iso = geo.affiliation_country(_text(aff))
            if iso:
                aff_countries.append(iso)
        out[pmid] = {
            'year': year if year.isdigit() else '',
            'title': _text(article.find('ArticleTitle')) if article is not None else '',
            'journal': _text(article.find('Journal/ISOAbbreviation')) if article is not None else '',
            'pub_types': sorted(set(pub_types)),
            'mesh_indexed': mesh is not None,
            'geo_terms': sorted(set(geo_terms)),
            'study_countries': sorted(set(countries)),
            'regions': sorted(set(regions)),
            'affiliation_countries': sorted(set(aff_countries)),
            'origin_terms': sorted(set(origin_terms)),
            'schema': SCHEMA,
        }
    return out


def _needs_fetch(rec: dict | None, now: datetime) -> bool:
    if not rec or rec.get('schema') != SCHEMA:
        return True
    fetched = datetime.fromisoformat(rec.get('fetched_utc', '1970-01-01T00:00:00+00:00'))
    if not rec.get('mesh_indexed') and now - fetched > REFETCH_UNINDEXED_AFTER:
        return True
    return now - fetched > REFETCH_ALL_AFTER


def enrich(pmids, http_post, cache_file: Path = CACHE_FILE, log=print) -> tuple[dict, dict]:
    """Return ({pmid: record}, stats). `http_post(url, form_dict) -> bytes`."""
    cache_file = Path(cache_file)
    cache = json.loads(cache_file.read_text('utf-8')) if cache_file.exists() else {}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    wanted = sorted({str(p).strip() for p in pmids if str(p).strip().isdigit()}, key=int)
    todo = [p for p in wanted if _needs_fetch(cache.get(p), now)]
    params = {'db': 'pubmed', 'retmode': 'xml', 'tool': 'HumanResponseAtlas'}
    if os.environ.get('NCBI_EMAIL'):
        params['email'] = os.environ['NCBI_EMAIL']
    if os.environ.get('NCBI_API_KEY'):
        params['api_key'] = os.environ['NCBI_API_KEY']
    if todo:
        log(f'Fetching PubMed records for {len(todo):,} studies '
            f'({len(wanted) - len(todo):,} already cached) …')
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        xml_bytes = http_post(f'{EUTILS}/efetch.fcgi', {**params, 'id': ','.join(chunk)})
        parsed = parse_efetch(xml_bytes)
        for pmid in chunk:
            rec = parsed.get(pmid, {'missing': True, 'mesh_indexed': False, 'schema': SCHEMA})
            rec['fetched_utc'] = now.isoformat()
            cache[pmid] = rec
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache), 'utf-8')     # save progress as we go
        if (i // BATCH) % 10 == 9:
            log(f'  … {min(i + BATCH, len(todo)):,} of {len(todo):,}')
    stats = {'pmids': len(wanted), 'fetched_now': len(todo),
             'not_found': sum(1 for p in wanted if cache.get(p, {}).get('missing')),
             'eutils': EUTILS}
    return {p: cache[p] for p in wanted if p in cache}, stats

