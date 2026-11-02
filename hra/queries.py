"""Documented search strategy. Reports quote these strings exactly.

Each medicine is searched under its generic name plus recognised synonyms and trade
names (from ChEMBL), in three evidence categories:

* pgx      genes, variants, genotypes or pharmacogenetics
* efficacy randomised trials, meta-analyses and systematic reviews
* safety   adverse effects, adverse events and toxicity
"""
from __future__ import annotations

MAX_NAMES = 8   # generic + synonyms + trade names, to keep queries within API limits


def names_for(identity: dict | None, name: str) -> list[str]:
    names = [name.lower()]
    if identity:
        salts = set(identity.get('salt_forms', []))
        official = [x for x in identity.get('synonyms', []) if x not in salts and ' ' not in x]
        names = [identity['generic_name']] + official + \
                [t.lower() for t in identity.get('trade_names', [])] + names
    out = []
    for n in names:
        n = n.strip()
        if n and n not in out and len(n) > 2:
            out.append(n)
    return out[:MAX_NAMES]


def _q(name: str) -> str:
    return f'"{name}"' if (' ' in name or '-' in name) else name


def pubmed(names: list[str]) -> dict[str, str]:
    drug = ' OR '.join(f'{_q(n)}[tiab]' for n in names)
    drug = f'({drug})'
    return {
        'pgx': f'{drug} AND (pharmacogen*[tiab] OR genotyp*[tiab] OR polymorphism*[tiab] OR '
               f'allele*[tiab] OR "Pharmacogenetics"[MeSH] OR "Polymorphism, Genetic"[MeSH])',
        'efficacy': f'{drug} AND (randomized controlled trial[pt] OR meta-analysis[pt] OR '
                    f'systematic review[pt])',
        'safety': f'{drug} AND (adverse effects[sh] OR "Drug-Related Side Effects and Adverse '
                  f'Reactions"[MeSH] OR "adverse event*"[tiab] OR toxicity[tiab])',
    }


def europepmc(names: list[str]) -> dict[str, str]:
    drug = ' OR '.join(f'TITLE:{_q(n)} OR ABSTRACT:{_q(n)}' for n in names)
    drug = f'({drug})'
    return {
        'pgx': f'{drug} AND (ABSTRACT:pharmacogen* OR ABSTRACT:genotyp* OR '
               f'ABSTRACT:polymorphism* OR ABSTRACT:allele*)',
        'efficacy': f'{drug} AND (PUB_TYPE:"randomized controlled trial" OR '
                    f'PUB_TYPE:"meta-analysis" OR PUB_TYPE:"systematic review")',
        'safety': f'{drug} AND (ABSTRACT:"adverse event" OR ABSTRACT:"adverse events" OR '
                  f'ABSTRACT:toxicity OR MESH:"Drug-Related Side Effects and Adverse Reactions")',
    }


def clinicaltrials(names: list[str]) -> str:
    return ' OR '.join(_q(n) for n in names)
