"""Evidence categories, assigned by documented and testable rules (v2).

No category is inferred from an AI confidence score or from study-design counts alone.
Every assignment returns the evidence that supports it, so each claim can be traced to
specific guidelines, annotations or studies.

Changes from v1 (Atlas v0.7):
* Efficacy and safety are never called "Established" from counts of trials and reviews:
  what those studies found has not been evaluated. Above the "limited" threshold they are
  "Not assessed" until a person records a reviewed conclusion with its supporting studies.
* "Conflicting" is judged within one ClinPGx summary annotation (one variant or haplotype,
  one outcome), not across different variants and outcomes of a gene.
* ClinPGx levels 3 and 4 are "Limited indexed evidence"; only 2A/2B are "Emerging".
* A CPIC level counts only when it is backed by a published guideline (not provisional).
* Registered trials count as efficacy evidence only when they have posted results or a
  linked results publication.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .models import FAILED, NOT_SEARCHED, OK, UNAVAILABLE

ESTABLISHED, EMERGING, CONFLICTING = 'Established evidence', 'Emerging evidence', 'Conflicting evidence'
LIMITED, NOT_FOUND, NOT_ASSESSED = 'Limited indexed evidence', 'Evidence not found', 'Not assessed'
CATEGORY_ORDER = [ESTABLISHED, CONFLICTING, EMERGING, LIMITED, NOT_FOUND, NOT_ASSESSED]
RULES_VERSION = 'classification rules v2 (Atlas v0.8)'

LIMITED_MAX_STUDIES = 4
CONFLICT_MIN_EACH = 2
CONFLICT_MIN_SHARE = 1 / 3
LITERATURE_SOURCES = {'pgx': ['pubmed', 'europepmc', 'clinpgx'],
                      'efficacy': ['pubmed', 'europepmc', 'clinicaltrials'],
                      'safety': ['pubmed', 'europepmc']}
REVIEWED_FILE = Path(__file__).resolve().parents[1] / 'verification' / 'reviewed_conclusions.csv'

RULES = {
    'gene (pharmacogenomic association with this medicine)': [
        f'{ESTABLISHED}: a published CPIC guideline rates the gene–medicine pair level A or B '
        '(provisional levels without a guideline do not count), or a ClinPGx summary annotation '
        'for the pair is level 1A or 1B.',
        f'{CONFLICTING}: not established, and within at least one ClinPGx summary annotation '
        '(the same variant or haplotype and the same outcome) the underlying studies include at '
        f'least {CONFLICT_MIN_EACH} statistically significant and {CONFLICT_MIN_EACH} '
        'non-significant results, with non-significant results at least one third of those '
        'that state significance.',
        f'{EMERGING}: the strongest ClinPGx summary annotation is level 2A or 2B.',
        f'{LIMITED}: only ClinPGx level 3 or 4 annotations (single studies, case reports, '
        'non-significant or in vitro evidence).',
        f'{NOT_ASSESSED}: ClinPGx was not searched or failed.',
    ],
    'medicine and evidence type (pgx, efficacy, safety)': [
        f'{NOT_ASSESSED} (search): every source for that evidence type failed or was not searched.',
        f'{NOT_FOUND}: no relevant study found, and every source for that evidence type was '
        'searched successfully. Never given after a partial search.',
        f'{LIMITED}: 1 to {LIMITED_MAX_STUDIES} relevant unique studies.',
        'pgx: otherwise the strongest gene classification above, with that gene as the supporting '
        'evidence. Without ClinPGx annotations, more than '
        f'{LIMITED_MAX_STUDIES} studies are "{NOT_ASSESSED}" because gene associations in the '
        'wider literature are not yet extracted.',
        f'efficacy and safety: more than {LIMITED_MAX_STUDIES} relevant studies are '
        f'"{NOT_ASSESSED} (findings not yet evaluated)". The tool counts studies but does not '
        'yet judge what they found, so it never labels them established, emerging or conflicting '
        'on its own.',
        'A person can record a reviewed conclusion (verification/reviewed_conclusions.csv) with '
        'the PubMed IDs that support it. It is then shown, labelled "human-reviewed", with those '
        'studies as its evidence.',
        'Relevant trials: registered studies count as efficacy evidence only when they have '
        'posted results or a linked results publication.',
    ],
}


def _cite(kind: str, ident: str, url: str = '', **extra) -> dict:
    return {'type': kind, 'id': ident, 'url': url, **extra}


def gene_category(annotations: list[dict], cpic: dict | None, clinpgx_status: str) -> dict:
    """annotations: [{'id', 'level', 'url', 'variant', 'outcome', 'evidence': [{'pmid', 'significance'}]}]
    cpic: {'level', 'provisional', 'guideline', 'guideline_url', 'pmids'} or None."""
    out = {'supporting': []}
    if cpic and cpic.get('level') in ('A', 'A/B', 'B') and not cpic.get('provisional') \
            and cpic.get('guideline'):
        out['supporting'].append(_cite('CPIC guideline', cpic['guideline'], cpic.get('guideline_url', ''),
                                       level=cpic['level'], pmids=cpic.get('pmids', [])))
    top = [a for a in annotations if a['level'] in ('1A', '1B')]
    out['supporting'] += [_cite('ClinPGx summary annotation', a['id'], a['url'], level=a['level'],
                                variant=a['variant'], outcome=a['outcome']) for a in top]
    if out['supporting']:
        why = ('CPIC level ' + cpic['level'] + ' guideline' if out['supporting'][0]['type'] == 'CPIC guideline'
               else 'ClinPGx level ' + top[0]['level'])
        return {**out, 'category': ESTABLISHED, 'reason': why}
    if clinpgx_status != OK:
        return {**out, 'category': NOT_ASSESSED, 'reason': 'ClinPGx not searched'}
    for a in annotations:
        sig = [e for e in a['evidence'] if e['significance'] in ('yes', 'no')]
        yes = [e['pmid'] for e in sig if e['significance'] == 'yes']
        no = [e['pmid'] for e in sig if e['significance'] == 'no']
        if len(yes) >= CONFLICT_MIN_EACH and len(no) >= CONFLICT_MIN_EACH and \
                len(no) / len(sig) >= CONFLICT_MIN_SHARE:
            out['supporting'].append(_cite('ClinPGx summary annotation', a['id'], a['url'], level=a['level'],
                                           variant=a['variant'], outcome=a['outcome'],
                                           significant_pmids=sorted(set(yes)),
                                           non_significant_pmids=sorted(set(no))))
    if out['supporting']:
        a = out['supporting'][0]
        return {**out, 'category': CONFLICTING,
                'reason': f"{a['variant']} / {a['outcome']}: {len(a['significant_pmids'])} studies "
                          f"significant vs {len(a['non_significant_pmids'])} not"}
    if not annotations:
        return {**out, 'category': NOT_FOUND, 'reason': 'no ClinPGx annotation'}
    best = min(a['level'] for a in annotations)
    keep = [a for a in annotations if a['level'] == best]
    out['supporting'] = [_cite('ClinPGx summary annotation', a['id'], a['url'], level=a['level'],
                               variant=a['variant'], outcome=a['outcome']) for a in keep]
    if best in ('2A', '2B'):
        return {**out, 'category': EMERGING, 'reason': f'strongest ClinPGx level {best}'}
    return {**out, 'category': LIMITED, 'reason': f'only ClinPGx level {best} annotations'}


def is_rct(types: list[str]) -> bool:
    t = ' '.join(types).lower()
    return 'randomized controlled trial' in t or 'randomised controlled trial' in t


def is_review(types: list[str]) -> bool:
    t = ' '.join(types).lower()
    return 'meta-analysis' in t or 'systematic review' in t


def relevant(cat: str, s) -> bool:
    if s.kind == 'trial':        # a registration alone is not evidence of an effect
        return cat == 'efficacy' and s.trial_has_results
    return cat in s.categories


def load_reviewed(path: Path = REVIEWED_FILE) -> list[dict]:
    if not Path(path).exists():
        return []
    rows = []
    for r in csv.DictReader(open(path, encoding='utf-8')):
        pmids = [p.strip() for p in (r.get('supporting_pmids') or '').replace(',', ';').split(';') if p.strip()]
        if r.get('classification') in CATEGORY_ORDER and pmids and r.get('reviewer'):
            rows.append({**r, 'supporting_pmids': pmids})
    return rows


def category_for(cat: str, studies: list, statuses: dict[str, str], genes: list[dict] | None = None,
                 reviewed: list[dict] | None = None, medicine: str = '') -> dict:
    srcs = LITERATURE_SOURCES[cat]
    ok = [s for s in srcs if statuses.get(s) == OK]
    bad = [s for s in srcs if statuses.get(s) in (FAILED, NOT_SEARCHED, UNAVAILABLE, None)]
    mine = [s for s in studies if relevant(cat, s)]
    n = len(mine)
    rcts = [s.key for s in mine if is_rct(s.publication_types)]
    reviews = [s.key for s in mine if is_review(s.publication_types)]
    base = {'unique_studies': n, 'sources_searched': ok, 'sources_missing': bad,
            'partial_search': bool(ok and bad), 'method': 'rule', 'rules': RULES_VERSION,
            'randomised_trials': len(rcts), 'reviews_or_meta_analyses': len(reviews),
            'supporting': {'studies': sorted(s.key for s in mine), 'randomised_trials': rcts,
                           'reviews_or_meta_analyses': reviews},
            'registered_trials_without_results': sorted(
                s.key for s in studies if s.kind == 'trial' and not s.trial_has_results)
            if cat == 'efficacy' else []}
    for r in reviewed or []:
        if r.get('medicine', '').lower() == medicine and r.get('category') == cat:
            return {**base, 'category': r['classification'], 'method': 'human-reviewed',
                    'reason': f"reviewed by {r['reviewer']} on {r.get('reviewed_on', '')}: {r.get('summary', '')}",
                    'supporting': {**base['supporting'], 'reviewed_pmids': r['supporting_pmids']}}
    if not ok:
        return {**base, 'category': NOT_ASSESSED, 'reason': 'no source for this evidence type could be searched'}
    if n == 0:
        if bad:
            return {**base, 'category': NOT_ASSESSED,
                    'reason': f'nothing found in {", ".join(ok)}, but {", ".join(bad)} could not be searched'}
        return {**base, 'category': NOT_FOUND, 'reason': f'no relevant study found in {", ".join(ok)}'}
    if n <= LIMITED_MAX_STUDIES:
        return {**base, 'category': LIMITED, 'reason': f'{n} relevant unique studies'}
    if cat == 'pgx' and genes:
        best = min(genes, key=lambda g: CATEGORY_ORDER.index(g['category']))
        if best['category'] in (ESTABLISHED, CONFLICTING, EMERGING, LIMITED):
            names = [g['gene'] for g in genes if g['category'] == best['category']]
            return {**base, 'category': best['category'],
                    'reason': f"strongest gene evidence: {', '.join(names[:6])} ({best['reason']})",
                    'supporting': {**base['supporting'], 'genes': names}}
    what = ('gene associations in the wider literature are not yet extracted' if cat == 'pgx' else
            f'{len(rcts)} randomised trials and {len(reviews)} reviews/meta-analyses identified; '
            'what they found has not been evaluated')
    return {**base, 'category': NOT_ASSESSED, 'reason': f'{n} relevant studies; findings not yet evaluated ({what})'}
