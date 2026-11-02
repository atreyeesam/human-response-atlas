"""Country boundaries and conservative country-name matching.

Two inputs are matched to ISO 3166 alpha-3 codes:

* PubMed MeSH geographic descriptors (e.g. "Japan", "England", "Georgia (Republic)")
  -> where a study was conducted / which place it is about, as indexed by NLM.
* Author affiliation strings -> where the research team is based.

Matching is deliberately exact (after normalisation). Ethnic-group or ancestry
MeSH terms such as "Asian People" or "African Americans" are never matched to
a country, and nothing here infers ancestry or nationality.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

GEO_DIR = Path(__file__).parent / 'data' / 'geo'
COUNTRIES_FILE = GEO_DIR / 'countries.geojson'

# MeSH and common-usage names that differ from Natural Earth's names.
EXTRA_ALIASES = {
    'USA': ['united states', 'usa', 'u s a', 'united states of america'],
    'GBR': ['united kingdom', 'uk', 'u k', 'great britain', 'england', 'scotland', 'wales',
            'northern ireland', 'london'],
    'KOR': ['republic of korea', 'korea', 'south korea', 'korea republic of', 'korea south',
            'korea (south)'],
    'PRK': ["democratic people's republic of korea", 'north korea'],
    'CHN': ['china', "people's republic of china", 'pr china', 'p r china', 'prc',
            'peoples republic of china', 'beijing', 'shanghai'],
    'TWN': ['taiwan', 'republic of china', 'taiwan roc', 'taiwan r o c'],
    'HKG': ['hong kong', 'hong kong sar', 'hong kong sar china'],
    'MAC': ['macau', 'macao'],
    'RUS': ['russia', 'russian federation'],
    'CZE': ['czech republic', 'czechia'],
    'VNM': ['vietnam', 'viet nam'],
    'IRN': ['iran', 'islamic republic of iran', 'iran islamic republic of'],
    'SYR': ['syria', 'syrian arab republic'],
    'LAO': ['laos', "lao people's democratic republic", 'lao pdr'],
    'TUR': ['turkey', 'turkiye', 'türkiye'],
    'NLD': ['netherlands', 'the netherlands', 'holland'],
    'CIV': ["cote d'ivoire", 'ivory coast', "côte d'ivoire"],
    'COD': ['democratic republic of the congo', 'dr congo', 'drc', 'congo democratic republic'],
    'COG': ['congo', 'republic of the congo', 'congo republic'],
    'TZA': ['tanzania', 'united republic of tanzania'],
    'MKD': ['north macedonia', 'republic of north macedonia', 'macedonia',
            'macedonia (republic)'],
    'MDA': ['moldova', 'republic of moldova'],
    'SWZ': ['eswatini', 'swaziland'],
    'CPV': ['cabo verde', 'cape verde'],
    'MMR': ['myanmar', 'burma'],
    'BRN': ['brunei', 'brunei darussalam'],
    'GEO': ['georgia (republic)', 'republic of georgia'],
    'BOL': ['bolivia'],
    'VEN': ['venezuela'],
    'PSE': ['palestine', 'state of palestine', 'west bank', 'gaza strip'],
    'SAU': ['saudi arabia', 'kingdom of saudi arabia', 'ksa'],
    'ARE': ['united arab emirates', 'uae', 'u a e'],
    'BIH': ['bosnia and herzegovina', 'bosnia-herzegovina'],
    'FSM': ['micronesia', 'federated states of micronesia'],
    'IRL': ['ireland', 'republic of ireland'],
    'PRI': ['puerto rico'],
}

# Sub-national MeSH descriptors / affiliation fragments that identify a country.
US_STATES = ['alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado',
             'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho', 'illinois',
             'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana', 'maine', 'maryland',
             'massachusetts', 'michigan', 'minnesota', 'mississippi', 'missouri', 'montana',
             'nebraska', 'nevada', 'new hampshire', 'new jersey', 'new mexico', 'new york',
             'north carolina', 'north dakota', 'ohio', 'oklahoma', 'oregon', 'pennsylvania',
             'rhode island', 'south carolina', 'south dakota', 'tennessee', 'texas', 'utah',
             'vermont', 'virginia', 'washington', 'west virginia', 'wisconsin', 'wyoming',
             'district of columbia', 'new york city', 'boston', 'chicago', 'los angeles',
             'san francisco', 'philadelphia', 'baltimore', 'new orleans']
CA_PROVINCES = ['ontario', 'quebec', 'british columbia', 'alberta', 'manitoba', 'saskatchewan',
                'nova scotia', 'new brunswick', 'newfoundland and labrador', 'prince edward island']
EXTRA_ALIASES['USA'] += US_STATES
EXTRA_ALIASES['CAN'] = ['canada'] + CA_PROVINCES

# Region-level geographic terms: recorded as a region, never assigned to a country.
REGION_TERMS = {
    'africa', 'africa south of the sahara', 'africa, northern', 'africa, western',
    'africa, eastern', 'africa, central', 'africa, southern', 'asia', 'asia, eastern',
    'asia, southeastern', 'asia, central', 'asia, western', 'asia, southern', 'europe',
    'europe, eastern', 'latin america', 'south america', 'central america', 'north america',
    'caribbean region', 'west indies', 'middle east', 'mediterranean region', 'arctic regions',
    'scandinavian and nordic countries', 'pacific islands', 'oceania', 'australasia',
    'developing countries', 'developed countries', 'indian ocean islands', 'baltic states',
    'transcaucasia', 'balkan peninsula', 'borneo', 'melanesia', 'micronesia (region)',
    'polynesia', 'americas',
}


def norm(text: str) -> str:
    text = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode()
    text = text.lower().strip()
    text = re.sub(r'[.\s]+$', '', text)
    text = re.sub(r'\s+', ' ', text.replace('.', ' ').replace('_', ' '))
    return text.strip()


@lru_cache(maxsize=1)
def countries() -> dict:
    return json.loads(COUNTRIES_FILE.read_text('utf-8'))


@lru_cache(maxsize=1)
def country_table() -> dict[str, dict]:
    """iso3 -> {name, continent, region_un, subregion}."""
    out = {}
    for f in countries()['features']:
        p = f['properties']
        out.setdefault(p['iso3'], {k: p[k] for k in ('name', 'continent', 'region_un',
                                                    'subregion')})
    return out


@lru_cache(maxsize=1)
def alias_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for f in countries()['features']:
        p = f['properties']
        if p['iso3'] in ('-99', ''):
            continue
        for key in ('name', 'name_long', 'admin', 'formal_en', 'name_alt'):
            if p.get(key):
                idx.setdefault(norm(p[key]), p['iso3'])
    for iso, names in EXTRA_ALIASES.items():
        for n in names:
            idx[norm(n)] = iso      # explicit aliases win over Natural Earth names
    # 'georgia' alone is the US state in MeSH; the country is 'Georgia (Republic)'.
    idx['georgia'] = 'USA'
    for r in REGION_TERMS:
        idx.pop(norm(r), None)
    return idx


def mesh_to_country(descriptor: str) -> tuple[str | None, str | None]:
    """Return (iso3, region) for a MeSH descriptor name; (None, None) if not geographic."""
    n = norm(descriptor)
    if n in {norm(r) for r in REGION_TERMS}:
        return None, descriptor
    return alias_index().get(n), None


# 'Georgia' in an address may be the US state or the country: leave unassigned.
_AMBIGUOUS_IN_ADDRESSES = {'georgia'}
_EMAIL = re.compile(r'\S+@\S+')
_TRAIL = re.compile(r'(electronic address:.*$)', re.I)


def affiliation_country(affiliation: str) -> str | None:
    """Best-effort country of an author affiliation string (last segment first)."""
    if not affiliation:
        return None
    text = _TRAIL.sub('', _EMAIL.sub('', affiliation))
    parts = [p for p in re.split(r'[,;]', text) if p.strip()]
    idx = alias_index()
    for part in reversed(parts[-3:]):
        n = norm(re.sub(r'\b\d[\d\- ]*\b', ' ', part))      # drop postcodes
        if n in idx and n not in _AMBIGUOUS_IN_ADDRESSES:
            return idx[n]
        # 'Seoul 03080 Republic of Korea' / 'Tokyo Japan'
        words = n.split()
        for k in range(min(5, len(words)), 0, -1):
            tail = ' '.join(words[-k:])
            if tail in idx and len(tail) > 2 and tail not in _AMBIGUOUS_IN_ADDRESSES:
                return idx[tail]
    return None


@lru_cache(maxsize=1)
def _text_pattern():
    names = [n for n in alias_index() if len(n) > 3 and n not in _AMBIGUOUS_IN_ADDRESSES]
    names += ['usa', 'uk', 'prc']
    return re.compile(r'\b(' + '|'.join(sorted(map(re.escape, names), key=len, reverse=True)) + r')\b')


def countries_in_text(text: str) -> list[str]:
    """Countries named anywhere in a short phrase (whole-word matches only)."""
    found = {alias_index()[m.group(1)] for m in _text_pattern().finditer(norm(text).replace(',', ' '))}
    return sorted(found)
