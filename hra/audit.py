"""Evidence-integrity audit: every population, geography, classification or effect claim in a
report must trace to identifiable supporting evidence.

Checks
------
1. Every count in the population and geography layers lists its supporting studies, the
   number of studies equals the count (participant totals equal the sum of the registry
   values), and every listed study exists in the report with at least one source link.
2. Every evidence classification lists its supporting studies; "relevant unique studies"
   equals that list; human-reviewed conclusions name their PubMed IDs; "Evidence not found"
   only follows a complete search.
3. Every gene classification other than "not found"/"not assessed" cites at least one
   guideline or ClinPGx annotation with an identifier.
4. Every extracted value can be found in its quote (numbers for sample sizes and effect
   estimates; the phrase for population descriptions).
"""
from __future__ import annotations

import re

from .classify import NOT_ASSESSED, NOT_FOUND


def _digits(s: str) -> list[str]:
    return re.findall(r'\d+(?:\.\d+)?', s.replace(',', ''))


def audit(report: dict, studies: list, extractions: list) -> dict:
    problems, checked = [], 0
    known = {s.key: s for s in studies}

    def check_layer(section, name, layer):
        nonlocal checked
        if not isinstance(layer, dict):
            return
        for label, v in layer.items():
            checked += 1
            ev = v.get('evidence', []) if isinstance(v, dict) else None
            if ev is None:
                problems.append(f'{section} / {name} / {label}: no supporting evidence listed')
                continue
            missing = [k for k in ev if k not in known or not known[k].sources]
            if missing:
                problems.append(f'{section} / {name} / {label}: unknown studies {missing[:3]}')
            if v['unit'] == 'studies' and v['count'] != len(set(ev)):
                problems.append(f'{section} / {name} / {label}: count {v["count"]} but {len(set(ev))} studies listed')
            if v['unit'] == 'participants':
                total = sum(b['participants'] for k in set(ev) for b in known[k].registry_race_ethnicity
                            if b['category'] == label) if not missing else None
                if total is not None and total != v['count']:
                    problems.append(f'{section} / {name} / {label}: {v["count"]} participants but evidence sums to {total}')

    for section in ('population', 'geography'):
        for name, layer in report[section].items():
            check_layer(section, name, layer)

    for cat, v in report['evidence_categories'].items():
        checked += 1
        sup = v.get('supporting') or {}
        studies_ = sup.get('studies', [])
        if v['unique_studies'] != len(studies_):
            problems.append(f'{cat}: {v["unique_studies"]} studies claimed but {len(studies_)} listed')
        if any(k not in known for k in studies_):
            problems.append(f'{cat}: lists studies not in the report')
        if v.get('method') == 'human-reviewed' and not sup.get('reviewed_pmids'):
            problems.append(f'{cat}: human-reviewed conclusion without PubMed IDs')
        if v['category'] == NOT_FOUND and v.get('sources_missing'):
            problems.append(f'{cat}: "not found" after a partial search')

    for g in report['genes']:
        checked += 1
        if g['category'] not in (NOT_FOUND, NOT_ASSESSED) and not any(
                c.get('id') for c in g.get('supporting', [])):
            problems.append(f'gene {g["gene"]}: {g["category"]} without a cited guideline or annotation')

    for e in extractions:
        if not e.field.startswith('stated_'):
            continue
        checked += 1
        q = e.quote.replace(',', '')
        if e.field in ('stated_sample_size', 'stated_effect_estimate'):
            if not all(d in q for d in _digits(e.value)):
                problems.append(f'{e.study_key}: {e.field} "{e.value}" not found in its quote')
        elif e.field == 'stated_population' and e.value.lower() not in e.quote.lower():
            problems.append(f'{e.study_key}: population "{e.value}" not found in its quote')
        elif e.field == 'stated_recruitment_country' and not e.quote:
            problems.append(f'{e.study_key}: recruitment country without a quote')
    return {'checked_claims': checked, 'problems': problems, 'passed': not problems}
