"""Cross-database de-duplication.

Records are linked when they share a PMID, DOI, PMCID or trial registration number
(a trial is linked to a paper only through the paper's own registration number or the
trial's RESULT references), or when two publications have the same normalised title and
year. Linked records form one Study that keeps every source reference.
"""
from __future__ import annotations

import re
import unicodedata

from .models import Record, Study


def norm_title(t: str) -> str:
    t = unicodedata.normalize('NFKD', t or '').encode('ascii', 'ignore').decode().lower()
    t = re.sub(r'<[^>]+>', ' ', t)
    return ' '.join(re.sub(r'[^a-z0-9 ]+', ' ', t).split())


def norm_doi(d: str) -> str:
    d = (d or '').strip().lower()
    return re.sub(r'^(https?://(dx\.)?doi\.org/|doi:)', '', d)


def keys_for(r: Record) -> set[str]:
    k = set()
    if r.pmid:
        k.add(f'pmid:{r.pmid}')
    if r.doi:
        k.add(f'doi:{norm_doi(r.doi)}')
    if r.pmcid:
        k.add(f'pmcid:{r.pmcid.upper()}')
    for n in r.nct_ids:
        k.add(f'nct:{n.upper()}')
    for p in r.extra.get('linked_pmids', []):
        k.add(f'pmid:{p}')
    if r.kind != 'trial' and r.year and len(norm_title(r.title)) > 25:
        k.add(f'title:{norm_title(r.title)}|{r.year}')
    return k


def deduplicate(records: list[Record]) -> list[Study]:
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[str, int] = {}
    for i, r in enumerate(records):
        for k in keys_for(r):
            if k in owner:
                a, b = find(i), find(owner[k])
                if a != b:
                    parent[a] = b
            else:
                owner[k] = i
    groups: dict[int, list[Record]] = {}
    for i, r in enumerate(records):
        groups.setdefault(find(i), []).append(r)

    studies = []
    order = {'pubmed': 0, 'clinpgx': 1, 'europepmc': 2, 'clinicaltrials': 3}
    for members in groups.values():
        members.sort(key=lambda r: order.get(r.source, 9))
        lead = next((m for m in members if m.kind != 'trial'), members[0])
        ids = {'pmid': set(), 'doi': set(), 'pmcid': set(), 'nct': set()}
        for m in members:
            if m.pmid: ids['pmid'].add(m.pmid)
            if m.doi: ids['doi'].add(norm_doi(m.doi))
            if m.pmcid: ids['pmcid'].add(m.pmcid.upper())
            ids['nct'] |= {n.upper() for n in m.nct_ids}
        trial = next((m for m in members if m.kind == 'trial'), None)
        key = (f"pmid:{min(ids['pmid'], key=int)}" if ids['pmid'] else
               f"nct:{min(ids['nct'])}" if ids['nct'] else
               f"doi:{min(ids['doi'])}" if ids['doi'] else f'{lead.source}:{lead.source_id}')
        studies.append(Study(
            key=key, title=lead.title, year=lead.year or (trial.year if trial else None),
            kind='trial' if all(m.kind == 'trial' for m in members) else
                 ('preprint' if all(m.kind == 'preprint' for m in members) else 'publication'),
            identifiers={k: sorted(v) for k, v in ids.items()},
            sources=[{'source': m.source, 'source_id': m.source_id, 'url': m.url} for m in members],
            categories=sorted({c for m in members for c in m.categories}),
            publication_types=sorted({p for m in members for p in m.publication_types if p}),
            countries=sorted({c for m in members if m.kind == 'trial' for c in m.countries}),
            enrollment=trial.enrollment if trial else None,
            registry_race_ethnicity=trial.registry_race_ethnicity if trial else [],
            licence_notes=sorted({f'{m.source}: {m.licence}' for m in members if m.licence}),
            trial_has_results=any(m.kind == 'trial' and m.extra.get('has_results') for m in members)))
    return sorted(studies, key=lambda s: (-(s.year or 0), s.key))
