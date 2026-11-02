"""Deterministic extraction (Phase 1 of the hybrid pipeline).

Every value keeps the exact quote, its character offsets, the rule that produced it and a
verification status. Rules only capture what a text states; nothing is inferred. In
particular, a population description is recorded as written ("Han Chinese patients") and is
never mapped to an ancestry group, and ancestry is never derived from author affiliation,
study location or nationality.

Rule versions are part of the method name, so results stay reproducible when rules change.
"""
from __future__ import annotations

import re

import geo
from .models import SOURCE_STRUCTURED, UNVERIFIED, Extraction, Record

PEOPLE = (r'patients|participants|subjects|individuals|volunteers|healthy volunteers|cases|'
          r'controls|children|adults|women|men|infants|neonates|people|persons|adolescents')
NUM = r'(\d{1,3}(?:,\d{3})+|\d+)'
SAMPLE = re.compile(
    rf'(?:\bn\s*=\s*{NUM})|(?:\b{NUM}\s+(?:[A-Za-z][\w-]*\s+){{0,3}}?(?:{PEOPLE})\b)', re.I)

# Population descriptors as authors write them. Recorded verbatim, never re-mapped.
DESCRIPTORS = [
    'Han Chinese', 'Chinese', 'Japanese', 'Korean', 'Taiwanese', 'Thai', 'Vietnamese', 'Malay',
    'Malaysian', 'Filipino', 'Indonesian', 'Singaporean', 'East Asian', 'South Asian', 'Asian',
    'Indian', 'Pakistani', 'Bangladeshi', 'Sri Lankan', 'Nepali', 'Nepalese',
    'Arab', 'Egyptian', 'Iranian', 'Turkish', 'Lebanese', 'Saudi', 'Emirati', 'Jordanian',
    'Israeli', 'Ashkenazi Jewish', 'Middle Eastern', 'North African',
    'Nigerian', 'Ghanaian', 'Kenyan', 'Ethiopian', 'Ugandan', 'Tanzanian', 'Zimbabwean',
    'South African', 'Sub-Saharan African', 'African', 'African American', 'Afro-Caribbean',
    'Black', 'White', 'Caucasian', 'European', 'European American', 'Northern European',
    'Hispanic', 'Latino', 'Latina', 'Latin American', 'Mexican', 'Brazilian', 'Puerto Rican',
    'Colombian', 'Peruvian', 'Native American', 'American Indian', 'Alaska Native', 'Indigenous',
    'Aboriginal', 'Torres Strait Islander', 'Maori', 'Pacific Islander', 'Polynesian', 'Inuit',
    'mixed ancestry', 'multi-ethnic', 'multiethnic',
]
DESC = re.compile(
    r'\b(' + '|'.join(sorted(map(re.escape, DESCRIPTORS), key=len, reverse=True)) + r')'
    r'(?:\s+(?:and|or)\s+[A-Z][\w-]+)?'
    rf'(?:\s+[\w-]+){{0,2}}?\s+(?:{PEOPLE}|population|populations|cohort|descent|ancestry|origin|'
    r'ethnicity|subjects)\b')
RECRUIT = re.compile(r'\b(?:conducted|performed|carried out|recruited|enrolled|undertaken|done)\s+'
                     r'(?:at|in|from|across)\s+([^.;]{3,120})', re.I)
EFFECT = re.compile(
    r'\b(odds ratio|hazard ratio|relative risk|risk ratio|OR|HR|RR|aOR|aHR)\b[^0-9]{0,12}'
    r'(\d+(?:\.\d+)?)\s*[,;(\[]?\s*(?:95\s*%\s*(?:CI|confidence interval)[:,]?\s*)'
    r'(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)')


def _quote(text: str, start: int, end: int, pad: int = 70) -> str:
    a, b = max(0, start - pad), min(len(text), end + pad)
    return ('…' if a else '') + text[a:b].strip() + ('…' if b < len(text) else '')


def from_abstract(study_key: str, r: Record) -> list[Extraction]:
    text, out = r.abstract or '', []
    if not text:
        return out
    loc = lambda m: f'abstract[{m.start()}:{m.end()}]'  # noqa: E731
    for m in SAMPLE.finditer(text):
        n = (m.group(1) or m.group(2)).replace(',', '')
        if not n.isdigit() or int(n) < 2 or 1900 <= int(n) <= 2100:
            continue                      # skip years and trivial numbers
        out.append(Extraction(study_key, 'stated_sample_size', n, r.source, r.source_id,
                              _quote(text, m.start(), m.end()), loc(m), 'rule:sample_size_v1'))
    seen = set()
    for m in DESC.finditer(text):
        val = m.group(0).strip()
        if val.lower() in seen:
            continue
        seen.add(val.lower())
        out.append(Extraction(study_key, 'stated_population', val, r.source, r.source_id,
                              _quote(text, m.start(), m.end()), loc(m), 'rule:population_description_v1'))
    for m in RECRUIT.finditer(text):
        phrase = m.group(1)
        countries = geo.countries_in_text(phrase)
        for c in countries:
            out.append(Extraction(study_key, 'stated_recruitment_country', c, r.source, r.source_id,
                                  _quote(text, m.start(), m.end()), loc(m), 'rule:recruitment_place_v1'))
    for m in EFFECT.finditer(text):
        val = f'{m.group(1)} {m.group(2)} (95% CI {m.group(3)}–{m.group(4)})'
        out.append(Extraction(study_key, 'stated_effect_estimate', val, r.source, r.source_id,
                              _quote(text, m.start(), m.end()), loc(m), 'rule:effect_estimate_v1'))
    return out


def from_structured(study_key: str, r: Record, curated_ancestry: dict) -> list[Extraction]:
    out = []
    if r.source == 'clinicaltrials':
        for c in r.countries:
            out.append(Extraction(study_key, 'registered_site_country', c, r.source, r.source_id,
                                  f'Location country: {c}', 'registry: contactsLocationsModule',
                                  'registry-structured', SOURCE_STRUCTURED))
        for b in r.registry_race_ethnicity:
            out.append(Extraction(study_key, 'registry_race_ethnicity',
                                  f"{b['category']}: {b['participants']}", r.source, r.source_id,
                                  f"{b['measure']} — {b['category']}: {b['participants']}",
                                  'registry: baselineCharacteristicsModule', 'registry-structured',
                                  SOURCE_STRUCTURED))
        if r.enrollment:
            out.append(Extraction(study_key, 'registered_enrollment', str(r.enrollment), r.source,
                                  r.source_id, f'Enrollment: {r.enrollment}', 'registry: designModule',
                                  'registry-structured', SOURCE_STRUCTURED))
    if r.source == 'clinpgx':
        for g in curated_ancestry.get(r.pmid, []):
            out.append(Extraction(study_key, 'curated_ancestry_group', g, r.source, r.source_id,
                                  f'ClinPGx biogeographical group: {g}', 'ClinPGx study parameters',
                                  'clinpgx-curated', 'curator-reviewed (ClinPGx)'))
    if r.source in ('pubmed', 'clinpgx'):
        for p in r.extra.get('mesh_places', []):
            out.append(Extraction(study_key, 'indexed_place', p, r.source, r.source_id,
                                  f'MeSH geographic heading: {p}', 'PubMed MeSH', 'nlm-indexing',
                                  SOURCE_STRUCTURED))
        for c in r.extra.get('affiliation_countries', []):
            out.append(Extraction(study_key, 'author_affiliation_country', c, r.source, r.source_id,
                                  f'Author affiliation country: {c}', 'PubMed affiliations',
                                  'rule:affiliation_country_v1', UNVERIFIED))
    return out
