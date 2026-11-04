"""AlphaGenome Atlas: AI-predicted functional impact of the variants in ClinPGx (optional).

    pip install alphagenome
    export ALPHAGENOME_API_KEY=...        # free, non-commercial key from DeepMind
    export NCBI_EMAIL=you@example.org
    python alphagenome_atlas.py

What it does
1. Takes every single-nucleotide variant (rsID) named in the loaded ClinPGx annotations.
2. Looks up its position on the GRCh38 genome in NCBI dbSNP (E-utilities esummary, SPDI notation).
   Star alleles (e.g. CYP2C19*2) are combinations of changes and are not scored.
3. Asks the AlphaGenome Atlas for its precomputed predictions for that exact DNA change, for every
   prediction type ("scorer") the Atlas offers.
4. Keeps a compact summary: for each scorer, the largest calibrated score (quantile) across all
   tissues, cell types and genes, and where it occurred. Raw prediction tracks are not stored.

Results are written to data/alphagenome/. The run can be stopped and restarted; finished variants
are not fetched again.

These are theoretical predictions from an AI model. They are not evidence that a variant changes
how anyone responds to a medicine, they are not validated for clinical use, and the Atlas never uses
them to classify evidence. AlphaGenome is provided under the AlphaGenome Terms of Use: non-commercial
use only, and not for clinical purposes or health decisions.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
DIR = HERE / 'data' / 'alphagenome'
VARIANTS_FILE, SCORES_FILE, SUMMARY_FILE = DIR / 'variants.csv', DIR / 'scores.csv', DIR / 'summary.csv'
MANIFEST_FILE, NOTICE_FILE = DIR / 'manifest.json', DIR / 'NOTICE.txt'

TERMS_URL = 'https://deepmind.google.com/science/alphagenome/terms'
TERMS_NOTICE = ('By using this information, you agree to the AlphaGenome Output Terms of Use '
                f'({TERMS_URL}).')
DISCLAIMER = ('AI predictions of how a DNA change may affect gene activity, from Google DeepMind\'s '
              'AlphaGenome Atlas. Theoretical modelling only: not evidence of an effect on any medicine, '
              'not validated for clinical use, and never used by the Atlas to classify evidence. '
              'Non-commercial use only. Summarised by Human Response Atlas: for each prediction type, '
              'only the largest calibrated score across tissues, cell types and genes is kept.')
EUTILS = os.environ.get('NCBI_EUTILS', 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils').rstrip('/')
RS = re.compile(r'^rs(\d+)$')
REFSEQ = {**{f'NC_{n:06d}': f'chr{n}' for n in range(1, 23)},
          'NC_000023': 'chrX', 'NC_000024': 'chrY', 'NC_012920': 'chrM'}
BASES = re.compile(r'^[ACGT]+$')


# ---- 1. variants -------------------------------------------------------------------
def rsids_from(associations: pd.DataFrame) -> list[str]:
    v = associations['variant'].astype(str).str.strip()
    return sorted(set(v[v.str.match(RS)]), key=lambda r: int(r[2:]))


def parse_spdi(spdi: str) -> dict | None:
    """'NC_000010.11:94781858:G:A' (0-based) -> chr10, 1-based position 94781859, G>A."""
    parts = spdi.strip().split(':')
    if len(parts) != 4:
        return None
    acc, pos, ref, alt = parts
    chrom = REFSEQ.get(acc.split('.')[0])
    if not chrom or not pos.isdigit() or not BASES.match(ref) or not BASES.match(alt):
        return None              # other assemblies, patches, insertions/deletions without anchor
    return {'chromosome': chrom, 'position': int(pos) + 1, 'ref': ref, 'alt': alt}


_HGVS = re.compile(r'(NC_0000\d\d)\.\d+:g\.(\d+)([ACGT])>([ACGT])')


def variants_from_docsum(rsid: str, doc: dict) -> list[dict]:
    rows = []
    for spdi in (doc.get('spdi') or '').split(','):
        if spdi and (p := parse_spdi(spdi)):
            rows.append({'rsid': rsid, **p})
    if not rows:     # fall back to the HGVS names in the document summary
        for acc, pos, ref, alt in _HGVS.findall(doc.get('docsum') or ''):
            if acc in REFSEQ:
                rows.append({'rsid': rsid, 'chromosome': REFSEQ[acc], 'position': int(pos),
                             'ref': ref, 'alt': alt})
    seen, out = set(), []
    for r in rows:
        k = (r['chromosome'], r['position'], r['ref'], r['alt'])
        if k not in seen:
            seen.add(k)
            out.append({**r, 'variant': f"{r['chromosome']}:{r['position']}:{r['ref']}>{r['alt']}"})
    return out


def _http_get(url: str, data: bytes | None = None) -> bytes:
    req = urllib.request.Request(url, data=data, headers={'User-Agent': 'HumanResponseAtlas'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def resolve(rsids: list[str], get=_http_get, batch: int = 200, pause: float = 0.6, log=print) -> pd.DataFrame:
    """Map rsIDs to GRCh38 single-nucleotide changes using dbSNP (NCBI E-utilities)."""
    rows, missing = [], []
    for i in range(0, len(rsids), batch):
        chunk = rsids[i:i + batch]
        params = {'db': 'snp', 'id': ','.join(r[2:] for r in chunk), 'retmode': 'json',
                  'tool': 'HumanResponseAtlas'}
        if os.environ.get('NCBI_EMAIL'):
            params['email'] = os.environ['NCBI_EMAIL']
        if os.environ.get('NCBI_API_KEY'):
            params['api_key'] = os.environ['NCBI_API_KEY']
        res = json.loads(get(f'{EUTILS}/esummary.fcgi', urllib.parse.urlencode(params).encode()))['result']
        for r in chunk:
            got = variants_from_docsum(r, res.get(r[2:], {}))
            rows += got
            if not got:
                missing.append(r)
        log(f'  dbSNP: {min(i + batch, len(rsids)):,} of {len(rsids):,} rsIDs looked up')
        time.sleep(pause)
    df = pd.DataFrame(rows, columns=['rsid', 'chromosome', 'position', 'ref', 'alt', 'variant'])
    df.attrs['not_mappable'] = missing
    return df


# ---- 2. scores -----------------------------------------------------------------------
def _label(var: pd.DataFrame, j: int) -> str:
    row = var.iloc[j]
    parts = [str(row[c]) for c in ('biosample_name', 'Assay title', 'name') if c in var and str(row[c])
             not in ('', 'nan')]
    return ' · '.join(dict.fromkeys(parts))[:160]


def summarise_anndata(rsid: str, variant: str, gene: str, scorer: str, ad) -> dict:
    """Largest calibrated score (quantile) for one scorer; falls back to raw scores if uncalibrated."""
    import numpy as np
    q = ad.layers['quantiles'] if 'quantiles' in getattr(ad, 'layers', {}) else None
    m = np.abs(np.asarray(q if q is not None else ad.X, dtype=float))
    out = {'rsid': rsid, 'variant': variant, 'scorer': scorer, 'calibrated': q is not None,
           'n_values': int(m.size), 'max_score': None, 'where': '', 'gene_scored': '',
           'max_score_for_annotated_gene': None}
    if not m.size or not np.isfinite(m).any():
        return out
    m = np.where(np.isfinite(m), m, -1)
    i, j = np.unravel_index(int(m.argmax()), m.shape)
    out['max_score'] = round(float(m[i, j]), 4)
    out['where'] = _label(ad.var, j)
    obs = ad.obs if ad.obs is not None else pd.DataFrame()
    if 'gene_name' in obs:
        out['gene_scored'] = str(obs.iloc[i]['gene_name'])
        mine = (obs['gene_name'].astype(str) == gene).to_numpy()
        if gene and mine.any():
            out['max_score_for_annotated_gene'] = round(float(m[mine].max()), 4)
    return out


def fetch_scores(variants: pd.DataFrame, client, scorers: list[str], genes: dict[str, str],
                 done: set | None = None, max_workers: int = 4, log=print, save=None) -> list[dict]:
    from alphagenome.data import genome
    done = done or set()
    todo = [r for r in variants.itertuples() if r.variant not in done]
    rows, errors = [], []

    def one(r):
        v = genome.Variant(r.chromosome, int(r.position), r.ref, r.alt, name=r.rsid)
        res = client.query_variant(v, requested_scorers=scorers)
        return [summarise_anndata(r.rsid, r.variant, genes.get(r.rsid, ''), s, ad) for s, ad in res.items()]

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(one, r): r for r in todo}
        for n, f in enumerate(as_completed(futs), 1):
            r = futs[f]
            try:
                got = f.result()
                rows += got or [{'rsid': r.rsid, 'variant': r.variant, 'scorer': '', 'max_score': None,
                                 'where': 'no prediction returned'}]
            except Exception as e:          # keep going; record the failure
                errors.append({'rsid': r.rsid, 'variant': r.variant, 'error': f'{type(e).__name__}: {e}'[:300]})
            if n % 50 == 0 or n == len(todo):
                log(f'  AlphaGenome: {n:,} of {len(todo):,} variants')
                if save:
                    save(rows)
    fetch_scores.errors = errors
    return rows


def summary(scores: pd.DataFrame) -> pd.DataFrame:
    """One row per variant: the strongest calibrated prediction across scorers."""
    s = scores.dropna(subset=['max_score']) if 'max_score' in scores else scores.iloc[0:0]
    if s.empty:
        return pd.DataFrame(columns=['rsid', 'variant', 'max_score', 'scorer', 'where', 'calibrated',
                                     'max_score_for_annotated_gene', 'scorers'])
    s = s.assign(_rank=s.calibrated.astype(bool).astype(int) * 10 + s.max_score)
    best = s.sort_values('_rank', ascending=False).groupby('variant', as_index=False).first()
    gene_best = s.groupby('variant').max_score_for_annotated_gene.max().rename('max_score_for_annotated_gene')
    n = s.groupby('variant').scorer.nunique().rename('scorers')
    best = best.drop(columns=['_rank', 'max_score_for_annotated_gene']).join(gene_best, on='variant').join(n, on='variant')
    return best[['rsid', 'variant', 'max_score', 'scorer', 'where', 'calibrated',
                 'max_score_for_annotated_gene', 'scorers']]


# ---- runner --------------------------------------------------------------------------
def run(api_key: str, associations: pd.DataFrame, client=None, get=_http_get, log=print,
        out: Path = DIR, max_workers: int = 4) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rsids = rsids_from(associations)
    log(f'{len(rsids):,} distinct rsIDs in the ClinPGx annotations.')
    vfile = out / VARIANTS_FILE.name
    if vfile.exists():
        variants = pd.read_csv(vfile, dtype={'position': int})
        new = [r for r in rsids if r not in set(variants.rsid)]
    else:
        variants, new = pd.DataFrame(columns=['rsid', 'chromosome', 'position', 'ref', 'alt', 'variant']), rsids
    not_mappable = []
    if new:
        got = resolve(new, get=get, log=log)
        not_mappable = got.attrs.get('not_mappable', [])
        variants = pd.concat([variants, got], ignore_index=True)
        variants.to_csv(vfile, index=False)
    if client is None:
        from alphagenome.atlas import atlas
        client = atlas.create(api_key)
    meta = client.scorer_metadata()
    scorers = sorted(meta)
    log(f'AlphaGenome Atlas offers {len(scorers)} prediction types: {", ".join(scorers)}')
    sfile = out / SCORES_FILE.name
    old = pd.read_csv(sfile) if sfile.exists() and sfile.stat().st_size else pd.DataFrame()
    done = set(old.variant) if len(old) else set()
    genes = associations.assign(variant=associations.variant.astype(str)).groupby('variant').gene.first().to_dict()

    def save(rows):
        pd.concat([old, pd.DataFrame(rows)], ignore_index=True).to_csv(sfile, index=False)

    rows = fetch_scores(variants, client, scorers, genes, done, max_workers, log, save)
    scores = pd.concat([old, pd.DataFrame(rows)], ignore_index=True)
    scores.to_csv(sfile, index=False)
    summ = summary(scores)
    summ.to_csv(out / SUMMARY_FILE.name, index=False)
    errors = getattr(fetch_scores, 'errors', [])
    try:
        from importlib.metadata import version
        client_version = version('alphagenome')
    except Exception:
        client_version = 'unknown'
    manifest = {
        'source': 'AlphaGenome Atlas (Google DeepMind)', 'terms': TERMS_URL, 'notice': TERMS_NOTICE,
        'disclaimer': DISCLAIMER, 'retrieved_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'client': f'alphagenome {client_version}', 'genome': 'GRCh38 (positions from NCBI dbSNP)',
        'scorers': {s: {'is_signed': getattr(m, 'is_signed', None)} for s, m in meta.items()},
        'rsids_in_clinpgx': len(rsids), 'variants_mapped': int(variants.variant.nunique()),
        'rsids_not_mappable_this_run': not_mappable, 'variants_scored': int(summ.variant.nunique()),
        'errors_this_run': errors[:50], 'error_count_this_run': len(errors),
    }
    (out / MANIFEST_FILE.name).write_text(json.dumps(manifest, indent=2), 'utf-8')
    (out / NOTICE_FILE.name).write_text(f'{TERMS_NOTICE}\n\n{DISCLAIMER}\n', 'utf-8')
    log(f"Done: {manifest['variants_scored']:,} variants scored; {len(errors):,} failed this run. "
        f'Results in {out}.')
    return manifest


def load(dir: Path = DIR) -> tuple[pd.DataFrame | None, dict | None]:
    """Summary table and manifest, or (None, None) if the scores have not been downloaded."""
    if not (dir / SUMMARY_FILE.name).exists():
        return None, None
    m = json.loads((dir / MANIFEST_FILE.name).read_text('utf-8')) if (dir / MANIFEST_FILE.name).exists() else {}
    return pd.read_csv(dir / SUMMARY_FILE.name), m


def main() -> int:
    key = os.environ.get('ALPHAGENOME_API_KEY', '').strip()
    if not key:
        print('Set ALPHAGENOME_API_KEY first (a free, non-commercial key from DeepMind).')
        return 1
    import atlas
    if not atlas.live_available():
        print('Download the ClinPGx data first (python ingest.py).')
        return 1
    run(key, atlas.load_live()['associations'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
