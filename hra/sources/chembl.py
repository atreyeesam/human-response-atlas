"""ChEMBL: standardised identifier, synonyms, trade names and mechanism of action."""
from __future__ import annotations

from ..http import SourceError
from ..models import FAILED, OK, Licence, SourceResult

BASE = 'https://www.ebi.ac.uk/chembl/api/data'
LICENCE = Licence('Creative Commons Attribution-ShareAlike 3.0 Unported (CC BY-SA 3.0)',
                  'https://creativecommons.org/licenses/by-sa/3.0/',
                  'ChEMBL data, EMBL-EBI. Cite: Zdrazil B, et al. Nucleic Acids Res 2024;52:D1180-92.')
USEFUL_SYNONYMS = {'INN', 'USAN', 'BAN', 'JAN', 'TRADE_NAME', 'FDA', 'USP', 'OTHER'}


def _norm(s: str) -> str:
    return ' '.join((s or '').lower().replace('-', ' ').split())


def pick_molecule(molecules: list[dict], name: str) -> dict | None:
    """Exact match on preferred name or any synonym; never a fuzzy guess."""
    n = _norm(name)
    for m in molecules:
        names = {_norm(m.get('pref_name') or '')} | {
            _norm(s.get('molecule_synonym', '')) for s in m.get('molecule_synonyms') or []}
        if n in names:
            return m
    return None


def resolve(name: str, http) -> tuple[dict | None, SourceResult]:
    """Return ({chembl_id, generic_name, synonyms, trade_names, max_phase, mechanisms}, status).

    ChEMBL often files brand names under a salt form (e.g. clopidogrel bisulfate, "Plavix")
    rather than the parent compound. The match is therefore moved to its parent molecule, and
    synonyms and trade names are collected from the parent and every salt form of it.
    """
    res = SourceResult('chembl', OK, licence=LICENCE)
    try:
        data = http.json(f'{BASE}/molecule/search.json', {'q': name, 'limit': 25})
        res.queries.append({'category': 'identity', 'query': f'molecule/search?q={name}',
                            'total': (data.get('page_meta') or {}).get('total_count', 0),
                            'retrieved': len(data.get('molecules') or [])})
        mol = pick_molecule(data.get('molecules') or [], name)
        if not mol:
            return None, res
        parent_id = ((mol.get('molecule_hierarchy') or {}).get('parent_chembl_id')
                     or mol['molecule_chembl_id'])
        parent = mol if parent_id == mol['molecule_chembl_id'] else \
            http.json(f'{BASE}/molecule/{parent_id}.json')
        family = http.json(f'{BASE}/molecule.json',
                           {'molecule_hierarchy__parent_chembl_id': parent_id, 'limit': 50})
        members = {m['molecule_chembl_id']: m for m in
                   [parent, mol] + list(family.get('molecules') or [])}
        syns = [s for m in members.values() for s in (m.get('molecule_synonyms') or [])]
        mech = http.json(f'{BASE}/mechanism.json', {'molecule_chembl_id': parent_id, 'limit': 50})
        info = {
            'chembl_id': parent_id,
            'matched_chembl_id': mol['molecule_chembl_id'],
            'generic_name': (parent.get('pref_name') or name).lower(),
            'salt_forms': sorted((m.get('pref_name') or k).lower() for k, m in members.items()
                                 if k != parent_id),
            'synonyms': sorted({s['molecule_synonym'].lower() for s in syns
                                if s.get('syn_type') in USEFUL_SYNONYMS - {'TRADE_NAME'}}),
            'trade_names': sorted({s['molecule_synonym'] for s in syns
                                   if s.get('syn_type') == 'TRADE_NAME'}, key=str.lower),
            'max_phase': parent.get('max_phase'),
            'mechanisms': [{'action': m.get('mechanism_of_action'),
                            'target_chembl_id': m.get('target_chembl_id'),
                            'action_type': m.get('action_type')}
                           for m in mech.get('mechanisms') or []],
            'url': f'https://www.ebi.ac.uk/chembl/explore/compound/{parent_id}',
        }
        return info, res
    except SourceError as e:
        res.status, res.error = FAILED, str(e)
        return None, res
