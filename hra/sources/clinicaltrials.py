"""ClinicalTrials.gov API v2: registered studies, site countries, linked PMIDs and
participant race/ethnicity as reported in posted results (registry categories, kept verbatim)."""
from __future__ import annotations

import re

from .. import queries
from ..http import SourceError
from ..models import FAILED, OK, Licence, Record, SourceResult

BASE = 'https://clinicaltrials.gov/api/v2/studies'
LICENCE = Licence('ClinicalTrials.gov terms and conditions (U.S. National Library of Medicine)',
                  'https://clinicaltrials.gov/about-site/terms-conditions',
                  'Registry records are provided by sponsors; NLM asks that ClinicalTrials.gov be '
                  'credited and that records are not presented as endorsed or verified by NLM.')
RACE = re.compile(r'race|ethnic', re.I)


def baseline_race_ethnicity(results: dict) -> list[dict]:
    """Participant counts by the registry's own race/ethnicity categories (no re-mapping)."""
    base = (results or {}).get('baselineCharacteristicsModule') or {}
    groups = {g.get('id'): g.get('title', '') for g in base.get('groups') or []}
    total_ids = [gid for gid, t in groups.items() if t.strip().lower() == 'total']
    out = []
    for m in base.get('measures') or []:
        if not RACE.search(m.get('title', '')):
            continue
        for cls in m.get('classes') or []:
            for cat in cls.get('categories') or []:
                vals = {x.get('groupId'): x.get('value') for x in cat.get('measurements') or []}
                pick = [vals[g] for g in total_ids if g in vals] or list(vals.values())
                try:
                    n = int(float(pick[0])) if len(pick) == 1 else int(sum(float(v) for v in pick))
                except (TypeError, ValueError):
                    continue
                out.append({'measure': m.get('title', ''),
                            'category': ' / '.join(x for x in (cls.get('title'), cat.get('title')) if x),
                            'participants': n})
    return out


def record_from_study(s: dict) -> Record:
    p = s.get('protocolSection') or {}
    ident = p.get('identificationModule') or {}
    nct = ident.get('nctId', '')
    design = p.get('designModule') or {}
    status = p.get('statusModule') or {}
    start = ((status.get('startDateStruct') or {}).get('date') or '')[:4]
    locs = (p.get('contactsLocationsModule') or {}).get('locations') or []
    refs = (p.get('referencesModule') or {}).get('references') or []
    phases = design.get('phases') or []
    return Record(
        source='clinicaltrials', source_id=nct, url=f'https://clinicaltrials.gov/study/{nct}',
        kind='trial', title=ident.get('briefTitle', ''), year=int(start) if start.isdigit() else None,
        nct_ids=[nct], publication_types=[design.get('studyType', '')] + phases,
        countries=sorted({l.get('country') for l in locs if l.get('country')}),
        enrollment=(design.get('enrollmentInfo') or {}).get('count'),
        registry_race_ethnicity=baseline_race_ethnicity(s.get('resultsSection')),
        extra={'overall_status': status.get('overallStatus', ''),
               'conditions': (p.get('conditionsModule') or {}).get('conditions') or [],
               # only the trial's own result papers; BACKGROUND references are other studies
               'linked_pmids': sorted({r['pmid'] for r in refs
                                       if r.get('pmid') and r.get('type') in ('RESULT', 'DERIVED')}),
               'has_results': bool(s.get('hasResults'))})


def search(names: list[str], http, max_records: int = 2000) -> SourceResult:
    res = SourceResult('clinicaltrials', OK, licence=LICENCE)
    q = queries.clinicaltrials(names)
    token, total = None, None
    try:
        while len(res.records) < max_records:
            params = {'query.intr': q, 'pageSize': min(1000, max_records - len(res.records)),
                      'countTotal': 'true', 'format': 'json'}
            if token:
                params['pageToken'] = token
            data = http.json(BASE, params)
            if 'studies' not in data:
                raise SourceError('ClinicalTrials.gov response had no studies list')
            total = data.get('totalCount', total)
            res.records += [record_from_study(s) for s in data['studies']]
            token = data.get('nextPageToken')
            if not token or not data['studies']:
                break
        res.queries.append({'category': 'trials', 'query': f'query.intr={q}',
                            'total': total if total is not None else len(res.records),
                            'retrieved': len(res.records)})
    except SourceError as e:
        res.status, res.error = FAILED, str(e)
    return res
