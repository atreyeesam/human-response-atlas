"""Run one medicine through every connected source and build a reproducible evidence report."""
from __future__ import annotations

import csv
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from . import __version__, classify, extract, queries
from .dedup import deduplicate
from .http import Http
from .models import FAILED, NOT_SEARCHED, OK, SourceResult, now_utc
from .sources import chembl, clinicaltrials, clinpgx, europepmc, pubmed

ALL_SOURCES = ('chembl', 'clinpgx', 'pubmed', 'europepmc', 'clinicaltrials')
QUESTION = ('What does the indexed research say about how people respond to {m}, which genetic '
            'factors have been studied, which populations were represented, and what remains unknown?')


class SearchResult:
    def __init__(self, report: dict, studies: list, extractions: list, records: list | None = None):
        self.report, self.studies, self.extractions = report, studies, extractions
        self.records = records or []      # in memory only (holds abstracts); never written to reports

    def write_report(self, out_dir) -> Path:
        from .report import write_all
        return write_all(self, Path(out_dir))


def _country(iso: str) -> str:
    import geo
    return geo.country_table().get(iso, {}).get('name', iso)


def search_medicine(name: str, http: Http | None = None, live_dir=None, clinpgx_data=None,
                    sources=ALL_SOURCES, max_per_category: int = 5000, max_trials: int = 2000,
                    log=None, reviewed_path=classify.REVIEWED_FILE) -> SearchResult:
    http = http or Http()
    say = log or (lambda *_: None)
    name = name.strip().lower()
    started = now_utc()
    results: dict[str, SourceResult] = {}

    # 1-2. Standardised name, synonyms and trade names
    identity = None
    if 'chembl' in sources:
        say('Looking up the medicine in ChEMBL …')
        t0 = time.monotonic()
        identity, results['chembl'] = chembl.resolve(name, http)
        results['chembl'].seconds = round(time.monotonic() - t0, 2)
    else:
        results['chembl'] = SourceResult('chembl', NOT_SEARCHED, licence=chembl.LICENCE)
    names = queries.names_for(identity, name)
    generic = identity['generic_name'] if identity else name

    # 3-4. Search every connected source
    curated, cpic_rows = {}, []
    if 'clinpgx' in sources:
        results['clinpgx'], results['cpic'], curated, cpic_rows = clinpgx.search(
            [generic] + names, live_dir, clinpgx_data)
    for key, fn, kw in (('pubmed', pubmed.search, {'max_per_category': max_per_category}),
                        ('europepmc', europepmc.search, {'max_per_category': max_per_category}),
                        ('clinicaltrials', clinicaltrials.search, {'max_records': max_trials})):
        if key in sources:
            say(f'Searching {key} …')
            t0 = time.monotonic()
            results[key] = fn(names, http, **kw)
            results[key].seconds = round(time.monotonic() - t0, 2)
        else:
            mod = {'pubmed': pubmed, 'europepmc': europepmc, 'clinicaltrials': clinicaltrials}[key]
            results[key] = SourceResult(key, NOT_SEARCHED, licence=mod.LICENCE)
    statuses = {k: r.status for k, r in results.items()}
    records = [rec for k, r in results.items() if r.status == OK for rec in r.records]

    # 5. De-duplicate across databases, keeping every source reference
    studies = deduplicate(records)
    by_record = {}
    for s in studies:
        for src in s.sources:
            by_record[(src['source'], src['source_id'])] = s.key

    # 4b. Extraction with provenance (rules only; nothing inferred)
    extractions = []
    for rec in records:
        k = by_record[(rec.source, rec.source_id)]
        extractions += extract.from_structured(k, rec, curated)
        if rec.source in ('pubmed', 'europepmc'):
            extractions += extract.from_abstract(k, rec)
    # the same abstract may come from PubMed and Europe PMC: keep one copy of each fact
    seen, uniq = set(), []
    for e in extractions:
        sig = (e.study_key, e.field, e.value.lower(), e.method)
        if sig not in seen:
            seen.add(sig)
            uniq.append(e)
    extractions = uniq
    for s in studies:
        s.extractions = [e for e in extractions if e.study_key == s.key]

    # 7. Gene-level classification (ClinPGx + CPIC), with the evidence for each call
    genes = []
    if clinpgx_data is None and statuses.get('clinpgx') == OK:
        clinpgx_data = clinpgx._load(live_dir)
    if clinpgx_data is not None and statuses.get('clinpgx') == OK:
        a = clinpgx_data['associations']
        a = a[a.drug.isin([generic] + names)]
        sp = clinpgx_data['study_populations'].drop_duplicates(['summary_annotation_id', 'variant_annotation_id'])
        ev_by_ann = {k: g[['pmid', 'significance']].to_dict('records')
                     for k, g in sp.groupby('summary_annotation_id')}
        for g, grp in a.groupby('gene'):
            anns = [{'id': r.summary_annotation_id, 'level': r.level_of_evidence, 'url': r.source_url,
                     'variant': r.variant, 'outcome': r.outcome,
                     'evidence': ev_by_ann.get(r.summary_annotation_id, [])}
                    for r in grp.drop_duplicates('summary_annotation_id').itertuples()]
            cp = next((r for r in cpic_rows if r['gene'] == g), None)
            cpic = None if cp is None else {
                'level': cp.get('cpic_level'), 'guideline': cp.get('cpic_guideline') or '',
                'guideline_url': cp.get('cpic_guideline_url') or '',
                'provisional': str(cp.get('cpic_provisional')).lower() == 'true',
                'pmids': [x for x in str(cp.get('cpic_pmids') or '').split(';') if x]}
            res_g = classify.gene_category(anns, cpic, OK)
            genes.append({'gene': g, **res_g, 'cpic_level': (cpic or {}).get('level') or '',
                          'cpic_provisional': (cpic or {}).get('provisional', False),
                          'clinpgx_best_level': min(x['level'] for x in anns) if anns else '',
                          'clinpgx_annotations': len(anns)})
        genes.sort(key=lambda x: (classify.CATEGORY_ORDER.index(x['category']), x['gene']))
    reviewed = classify.load_reviewed(reviewed_path) if reviewed_path else []
    categories = {c: classify.category_for(c, studies, statuses, genes if c == 'pgx' else None,
                                           reviewed, generic)
                  for c in ('pgx', 'efficacy', 'safety')}

    # 6. Population representation. Every count lists the studies (or trials) behind it.
    def layer(field, label=lambda v: v, unit='studies'):
        out = {}
        for st_ in studies:
            for v in {e.value for e in st_.extractions if e.field == field}:
                k = label(v)
                out.setdefault(k, {'count': 0, 'unit': unit, 'evidence': []})
                out[k]['count'] += 1
                out[k]['evidence'].append(st_.key)
        return dict(sorted(out.items(), key=lambda kv: -kv[1]['count']))
    race = {}
    for st_ in studies:
        for b in st_.registry_race_ethnicity:
            r = race.setdefault(b['category'], {'count': 0, 'unit': 'participants', 'evidence': []})
            r['count'] += b['participants']
            r['evidence'].append(st_.key)
    def informative(e):
        if e.field == 'curated_ancestry_group':
            return e.value not in ('Unknown', 'In vitro (no participants)')
        return e.field in ('stated_population', 'registry_race_ethnicity')
    has_pop = sorted(st_.key for st_ in studies if any(informative(e) for e in st_.extractions))
    population = {
        'curated_ancestry_groups (ClinPGx, curator-reviewed)': layer('curated_ancestry_group'),
        'registry_race_ethnicity_participants (ClinicalTrials.gov results, registry categories)':
            dict(sorted(race.items(), key=lambda kv: -kv[1]['count'])),
        'stated_population_descriptions (rule-extracted, unverified)': layer('stated_population'),
        'studies_with_any_population_information': len(has_pop),
        'studies_without_population_information': len(studies) - len(has_pop),
    }

    # 9. Geography: separate layers, never merged, each with its evidence
    no_geo = sorted(st_.key for st_ in studies if not any(
        e.field in ('registered_site_country', 'stated_recruitment_country', 'author_affiliation_country',
                    'indexed_place') for e in st_.extractions))
    geography = {
        '1_registered_trial_sites (registry)': layer('registered_site_country', _country),
        '1b_recruitment_country_stated_in_abstract (rule-extracted, unverified)':
            layer('stated_recruitment_country', _country),
        '2_author_affiliations': layer('author_affiliation_country', _country),
        '3_populations_described_in_reports': layer('stated_population'),
        '3b_place_indexed_by_pubmed (not proof of recruitment)':
            layer('indexed_place', lambda k: k if len(k) > 3 else _country(k)),
        '4_studies_with_no_geographic_information': len(no_geo),
    }

    # 11. Unresolved questions, phrased within the searched scope
    unresolved = []
    groups = {k: v['count'] for k, v in population['curated_ancestry_groups (ClinPGx, curator-reviewed)'].items()}
    for g in ('Central/South Asian', 'Sub-Saharan African', 'Near Eastern', 'Latino', 'Oceanian',
              'American', 'African American/Afro-Caribbean', 'East Asian', 'European'):
        if statuses.get('clinpgx') == OK and groups.get(g, 0) <= 1:
            unresolved.append(f'Few or no ClinPGx-curated studies of {generic} include {g} participants '
                              f'({groups.get(g, 0)} found). Wider literature not yet checked for this group.')
    for g in genes:
        if g['category'] in (classify.CONFLICTING, classify.EMERGING):
            unresolved.append(f'{g["gene"]}: {g["category"].lower()} ({g["reason"]}).')
    for c, v in categories.items():
        if v['category'] == classify.NOT_ASSESSED:
            unresolved.append(f'{c}: not assessed ({v["reason"]}).')

    failed = [k for k, s in statuses.items() if s == FAILED]
    limitations = [
        'Coverage describes the sources searched on the date shown, not all research ever done.',
        'Retrieval is capped per query; when a source reports more hits than were retrieved, '
        'counts are lower bounds (see "truncated" below).',
        'Rule-extracted values are unverified until checked against the publication.',
        'PubMed geographic indexing and author affiliations are not proof of where participants were recruited.',
        'Ancestry is never inferred from nationality, location or affiliation.',
    ] + ([f'These sources failed and were not used: {", ".join(failed)}. Results are incomplete.']
         if failed else [])

    source_rows = []
    for k in ('chembl', 'clinpgx', 'cpic', 'pubmed', 'europepmc', 'clinicaltrials'):
        r = results.get(k)
        if r is None:
            continue
        source_rows.append({
            'source': k, 'status': r.status, 'error': r.error, 'retrieved_at': r.retrieved_at,
            'seconds': r.seconds,
            'records_retrieved': len(r.records), 'total_hits_reported': r.total_hits,
            'truncated': any((q.get('total') or 0) > q.get('retrieved', 0) for q in r.queries),
            'queries': r.queries, 'licence': asdict(r.licence) if r.licence else None})

    report = {
        'medicine': generic, 'query_name': name,
        'question': QUESTION.format(m=generic),
        'identity': identity, 'search_names': names,
        'engine_version': __version__, 'started_at': started, 'finished_at': now_utc(),
        'sources': source_rows,
        'totals': {'records_retrieved': len(records), 'unique_studies': len(studies),
                   'by_source': {r['source']: r['records_retrieved'] for r in source_rows}},
        'evidence_categories': categories, 'genes': genes,
        'population': population, 'geography': geography,
        'unresolved_questions': unresolved, 'limitations': limitations,
        'classification_rules': classify.RULES, 'classification_rules_version': classify.RULES_VERSION,
        'no_geographic_information_evidence': no_geo,
        'reproduce': f'python -m hra search "{name}" --max {max_per_category} --max-trials {max_trials}',
    }
    from .audit import audit
    report['integrity'] = audit(report, studies, extractions)
    report['fingerprint'] = hashlib.sha256(json.dumps(
        {k: report[k] for k in ('medicine', 'search_names', 'engine_version')} |
        {'queries': [q['query'] for r in source_rows for q in r['queries']]}, sort_keys=True
    ).encode()).hexdigest()[:16]
    return SearchResult(report, studies, extractions, records)


def studies_rows(studies) -> list[dict]:
    return [{'study_key': s.key, 'title': s.title, 'year': s.year or '', 'kind': s.kind,
             'pmids': ';'.join(s.identifiers['pmid']), 'dois': ';'.join(s.identifiers['doi']),
             'nct_ids': ';'.join(s.identifiers['nct']),
             'found_in': ';'.join(sorted({x['source'] for x in s.sources})),
             'source_links': ' '.join(x['url'] for x in s.sources),
             'categories': ';'.join(s.categories), 'publication_types': ';'.join(s.publication_types),
             'registered_site_countries': ';'.join(s.countries),
             'registered_enrollment': s.enrollment or ''} for s in studies]


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        if not rows:
            f.write('')
            return
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
