import io
import json
import zipfile

import altair as alt
import pandas as pd
import streamlit as st

import atlas
import geo
import ingest
import alphagenome_atlas

st.set_page_config(page_title='Human Response Atlas', page_icon='🧭', layout='wide',
                   initial_sidebar_state='collapsed')

# --------------------------------------------------------------------------- #
# Design tokens
# --------------------------------------------------------------------------- #
INK, MUTED, TEAL, OCHRE, BLANK, LINE = '#1f2a37', '#5b6775', '#0e6e6b', '#c98f12', '#e1e5e4', '#d3dad8'
STATUS = {  # internal status -> (plain label, colour)
    'Available': ('Evidence available', TEAL),
    'Limited': ('Limited evidence', OCHRE),
    'Missing': ('No studies found', BLANK),
}
LABEL = {k: v[0] for k, v in STATUS.items()}
PUBMED = 'https://pubmed.ncbi.nlm.nih.gov/{}/'
ALL_MEDS, ALL_GENES = 'All medicines', 'All genes'

st.markdown(f"""
<style>
/* Fonts served by the app itself (SIL OFL 1.1): no requests to Google or other sites. */
@font-face {{ font-family: 'Public Sans'; font-weight: 400; font-style: normal; font-display: swap; src: url('app/static/fonts/public-sans-latin-400-normal.woff2') format('woff2'); }}
@font-face {{ font-family: 'Public Sans'; font-weight: 600; font-style: normal; font-display: swap; src: url('app/static/fonts/public-sans-latin-600-normal.woff2') format('woff2'); }}
@font-face {{ font-family: 'Public Sans'; font-weight: 700; font-style: normal; font-display: swap; src: url('app/static/fonts/public-sans-latin-700-normal.woff2') format('woff2'); }}
html, body, p, li, label, input, textarea, button, h1, h2, h3, h4, td, th,
[data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"] {{
  font-family: 'Public Sans', system-ui, sans-serif; }}
.block-container {{ padding-top: 3.2rem; max-width: 1280px; }}
h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
.hra-brand {{ display:flex; justify-content:space-between; align-items:baseline; gap:1rem;
  flex-wrap:wrap; border-bottom: 1px solid {LINE}; padding-bottom:.6rem; margin-bottom:1.4rem; }}
.hra-brand b {{ font-size:1.05rem; font-weight:700; color:{INK}; }}
.hra-brand span {{ color:{MUTED}; font-size:.85rem; }}
[data-testid="stMarkdownContainer"] p.hra-finding {{ font-size: clamp(1.6rem, 3.1vw, 2.45rem); line-height:1.18; font-weight:700;
  color:{INK}; max-width: 30ch; margin:0 0 .6rem 0; }}
[data-testid="stMarkdownContainer"] p.hra-sub {{ font-size:1.08rem; line-height:1.55; color:{MUTED}; max-width:68ch; margin-bottom:1.6rem; }}
.hra-key {{ display:flex; gap:1.2rem; flex-wrap:wrap; font-size:.88rem; color:{MUTED}; margin:.2rem 0 .4rem; }}
.hra-key i {{ display:inline-block; width:.8rem; height:.8rem; border-radius:2px; margin-right:.4rem;
  vertical-align:-1px; }}
.hra-pill {{ display:inline-block; padding:.12rem .55rem; border-radius:999px; font-size:.82rem;
  font-weight:600; }}
.hra-facts {{ display:grid; grid-template-columns: 1fr auto; row-gap:.35rem; column-gap:1rem;
  font-size:.95rem; margin:.8rem 0 1rem; }}
.hra-facts dt {{ color:{MUTED}; }} .hra-facts dd {{ margin:0; font-weight:600; text-align:right; }}
[data-testid="stMarkdownContainer"] .hra-note {{ font-size:.85rem; color:{MUTED}; line-height:1.5; }}
.hra-empty {{ max-width: 62ch; padding: 2.5rem 0 1rem; }}
[data-testid="stMarkdownContainer"] .hra-empty p:not(.hra-finding) {{ font-size:1.08rem; line-height:1.6; color:{MUTED}; }}
.hra-answers {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 17rem), 1fr));
  gap:1rem; margin: 1.6rem 0 1.2rem; }}
.hra-card {{ background:#ffffff; border:1px solid {LINE}; border-radius:8px; padding:1.2rem 1.3rem;
  display:grid; gap:.6rem; align-content:start; min-width:0; }}
.hra-card h3 {{ font-size:1.05rem; margin:0; padding:0; }}
.hra-card .hra-pill {{ justify-self:start; }}
.hra-card p {{ margin:0; line-height:1.55; }}
.hra-card a {{ color:{TEAL}; }}
.hra-means {{ border-left:3px solid {TEAL}; padding:.2rem 0 .2rem 1.2rem; margin:.4rem 0 1.4rem; max-width:70ch; }}
.hra-means h3 {{ font-size:1.05rem; margin:0 0 .4rem; padding:0; }}
.hra-means ul {{ margin:0; padding-left:1.1rem; }}
.hra-means li {{ margin:.3rem 0; line-height:1.55; }}
[data-testid="stTabs"] button p {{ font-size:1rem; font-weight:600; }}
footer, [data-testid="stDecoration"] {{ display:none; }}
</style>""", unsafe_allow_html=True)


def plural(n: int, word: str) -> str:
    many = word[:-1] + 'ies' if word.endswith('y') else word + 's'
    return f"{n:,} {word if n == 1 else many}"


def pill(status: str) -> str:
    label, colour = STATUS.get(status, (status, BLANK))
    fg = '#fff' if status in ('Available', 'Limited') else INK
    return f'<span class="hra-pill" style="background:{colour};color:{fg}">{label}</span>'


def key_legend() -> str:
    return '<div class="hra-key">' + ''.join(
        f'<span><i style="background:{c}"></i>{lab}</span>' for lab, c in STATUS.values()) + '</div>'


def footer():
    st.divider()
    st.markdown(
        '<p class="hra-note">Data from <a href="https://www.clinpgx.org">ClinPGx</a> (PharmGKB® and '
        f'CPIC®) under <a href="{LIC["url"]}">{LIC["short"]}</a> — '
        + ('<b>non-commercial use only</b> — ' if 'NC' in LIC['short'] else '')
        + '(CPIC content CC0); see the <a href="https://www.clinpgx.org/page/dataUsagePolicy">data '
        'usage policy</a>. Bibliographic data courtesy of the U.S. National Library of Medicine. Map: '
        'Natural Earth. No endorsement by ClinPGx, PharmGKB, CPIC or NLM is implied. CPIC® is a '
        'registered service mark of the U.S. Department of Health &amp; Human Services. For research '
        'only — not for clinical use, prescribing or individual patient decisions.</p>',
        unsafe_allow_html=True)


def run_download():
    with st.status('Downloading from ClinPGx, CPIC and PubMed — the first time takes a few minutes…',
                   expanded=True) as status:
        try:
            ingest.run(log=st.write)
            status.update(label='Data downloaded.', state='complete')
            st.cache_data.clear()
            st.session_state.pop('demo', None)
            st.rerun()
        except Exception as e:
            status.update(label='Download failed. Your previous data is unchanged.', state='error')
            st.error(f'{e}\n\nCheck your internet connection and try again. If it keeps failing, '
                     'copy this message and send it to whoever maintains the Atlas.')


# --------------------------------------------------------------------------- #
# Settings panel (hidden by default)
# --------------------------------------------------------------------------- #
has_live = atlas.live_available()
manifest = atlas.with_detected_licence(
    json.loads((atlas.LIVE_DIR / 'manifest.json').read_text('utf-8')), atlas.LIVE_DIR) \
    if has_live else None
LIC = atlas.clinpgx_licence(manifest)
with st.sidebar:
    st.header('Settings')
    if has_live:
        st.radio('Data source', ['ClinPGx + CPIC', 'Demo (invented data)'], key='source')
        st.caption(f"{atlas.release_label(manifest)}. Downloaded {manifest['accessed_utc'][:10]}.")
        if st.button('Update data', width='stretch'):
            run_download()
    st.subheader('What counts as “evidence available”')
    min_studies = st.number_input('At least this many studies', 1, 50, atlas.SPARSE_MIN_STUDIES)
    min_participants = st.number_input('…and at least this many participants', 0, 100000,
                                       atlas.SPARSE_MIN_PARTICIPANTS, step=50,
                                       help='Applied only where study sizes are reported.')
    shade = st.radio('Colour the map by', ['Evidence level', 'Number of studies'])

demo_mode = (not has_live and st.session_state.get('demo')) or \
            (has_live and st.session_state.get('source') == 'Demo (invented data)')

# --------------------------------------------------------------------------- #
# First run: no data yet
# --------------------------------------------------------------------------- #
if not has_live and not demo_mode:
    st.markdown('<div class="hra-brand"><b>Human Response Atlas</b>'
                '<span>Research prototype</span></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hra-empty"><p class="hra-finding">See where the evidence on genes and '
        'medicines comes from — and who is missing.</p><p>The Atlas maps the studies behind '
        'ClinPGx’s pharmacogenomic evidence: which countries they were done in, and which '
        'ancestry groups took part. To start, download the latest data from ClinPGx, CPIC and '
        'PubMed. It takes a few minutes and needs an internet connection.</p></div>',
        unsafe_allow_html=True)
    c1, c2, _ = st.columns([1.3, 1.3, 3])
    if c1.button('Download data', type='primary', width='stretch'):
        run_download()
    if c2.button('Explore sample data', width='stretch'):
        st.session_state['demo'] = True
        st.rerun()
    footer()
    st.stop()

# --------------------------------------------------------------------------- #
# Demo (invented data)
# --------------------------------------------------------------------------- #
if demo_mode:
    st.markdown('<div class="hra-brand"><b>Human Response Atlas</b>'
                '<span>Sample data — every record is invented</span></div>', unsafe_allow_html=True)
    st.warning('You are looking at invented sample records. Nothing here describes real research.')
    df = atlas.gaps(pd.read_csv(atlas.DEMO_FILE))
    chosen = st.selectbox('Medicine', sorted(df.drug.unique()))
    cur = df[df.drug == chosen].copy()
    cur['status'] = cur.coverage.map({'Records present in loaded dataset': 'Available',
                                      'Sparse in loaded dataset': 'Limited',
                                      'No records in loaded dataset': 'Missing'})
    cur['label'] = cur.status.map(LABEL)
    st.altair_chart(alt.Chart(cur).mark_bar().encode(
        y=alt.Y('population:N', sort='-x', title=None, axis=alt.Axis(labelLimit=300)),
        x=alt.X('study_count:Q', title='Invented study records', axis=alt.Axis(tickMinStep=1)),
        color=alt.Color('label:N', title=None, scale=alt.Scale(
            domain=[v[0] for v in STATUS.values()], range=[v[1] for v in STATUS.values()]),
            legend=alt.Legend(orient='bottom'))).properties(height=alt.Step(36)), width='stretch')
    if not has_live:
        if st.button('Download the real data instead', type='primary'):
            run_download()
    footer()
    st.stop()

# --------------------------------------------------------------------------- #
# Live data
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner='Loading the evidence…')
def _load(stamp):
    return atlas.load_live()


stamp = manifest['accessed_utc']
data = _load(stamp)
assoc = data['associations']


@st.cache_data(show_spinner=False)
def _studies(stamp, drug, gene):
    return atlas.studies(data, drug, gene)


@st.cache_data(show_spinner=False)
def _countries(stamp, drug, gene, basis, ms, mp):
    return atlas.country_coverage(_studies(stamp, drug, gene), basis, ms, mp)


@st.cache_data(show_spinner=False)
def _ancestry(stamp, drug, gene, ms, mp):
    groups = sorted(set(data['study_populations']['population']) - atlas.NON_GROUP_LABELS)
    return atlas.ancestry_coverage(_studies(stamp, drug, gene), ms, mp, groups)


GEO = json.loads(geo.COUNTRIES_FILE.read_text('utf-8'))

# ---- "Will this medicine work for me?" ----------------------------------------
# ClinPGx biogeographical groups, described in plain words for the public.
ANCESTRY_CHOICES = {
    'Central/South Asian': 'Central or South Asian: for example, families from India, Pakistan, '
                           'Bangladesh, Sri Lanka, Nepal or Central Asia',
    'East Asian': 'East Asian: for example, families from China, Japan, Korea or South-East Asia',
    'European': 'European: families from Europe',
    'Sub-Saharan African': 'Sub-Saharan African: families from Africa south of the Sahara',
    'African American/Afro-Caribbean': 'African American or Afro-Caribbean: African-descended '
                                       'families in the Americas or the Caribbean',
    'Near Eastern': 'Near Eastern: families from the Middle East or North Africa',
    'Latino': 'Latino: mixed heritage from Latin America',
    'American': 'Indigenous American: Indigenous peoples of the Americas',
    'Oceanian': 'Oceanian: Pacific Islander, Papuan or Indigenous Australian families',
}
CPIC_ORDER = ['A', 'A/B', 'B', 'B/C', 'C', 'C/D', 'D']


def _join(items: list[str]) -> str:
    items = list(dict.fromkeys(items))
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


def _card(question: str, status_html: str, body: str, note: str = '') -> str:
    return (f'<div class="hra-card"><h3>{question}</h3>{status_html}<p>{body}</p>'
            + (f'<p class="hra-note">{note}</p>' if note else '') + '</div>')


def _tag(text: str, tone: str) -> str:
    colours = {'good': (TEAL, '#fff'), 'warn': (OCHRE, '#fff'), 'none': (BLANK, INK),
               'info': ('#d8e6e4', INK)}
    bg, fg = colours[tone]
    return f'<span class="hra-pill" style="background:{bg};color:{fg}">{text}</span>'


def _go_explore(drug):
    st.session_state['mode'] = EXPLORE
    st.session_state['x_drug'] = drug


def gene_answer(drug: str) -> tuple[str, list[str]]:
    """Card 1. Returns (html, genes worth asking about)."""
    cp = atlas.cpic_for(data, drug)
    cp = cp[cp.cpic_level.isin(CPIC_ORDER)]
    strong = cp[cp.cpic_level.isin(['A', 'A/B'])]
    could = cp[cp.cpic_level.isin(['B', 'B/C'])]
    anns = atlas.annotations_for(data, drug)
    top = ingest.best_level(anns.level_of_evidence)
    links = ''.join(f'<br><a href="{u}" target="_blank" rel="noopener">{n}</a>'
                    for n, u in cp[cp.cpic_guideline != ''][['cpic_guideline', 'cpic_guideline_url']]
                    .drop_duplicates().itertuples(index=False))
    if len(strong):
        genes = sorted(strong.gene.tolist())
        return _card('Do genes affect this medicine?', _tag('Yes, with a prescribing guideline', 'good'),
                     f'An expert panel (CPIC) recommends that results of genetic tests for {_join(genes)} '
                     f'are used when prescribing {drug} (CPIC level A).',
                     'Guideline: ' + links if links else ''), genes
    if len(could):
        genes = sorted(could.gene.tolist())
        return _card('Do genes affect this medicine?', _tag('Yes, guidance available', 'good'),
                     f'An expert panel (CPIC) says results of genetic tests for {_join(genes)} could be used '
                     f'when prescribing {drug} (CPIC level B).',
                     'Guideline: ' + links if links else ''), genes
    if top in {'1A', '1B', '2A', '2B'}:
        genes = anns[anns.level_of_evidence.isin(['1A', '1B', '2A', '2B'])].gene.head(3).tolist()
        return _card('Do genes affect this medicine?', _tag('Possibly', 'warn'),
                     f'Studies link {_join(genes)} to how people respond to {drug}, but there is no '
                     'expert prescribing guideline for using genetic tests with it yet.'), []
    return _card('Do genes affect this medicine?', _tag('Not clearly', 'info'),
                 f'Only early or limited studies link genes to how people respond to {drug} '
                 f'(strongest ClinPGx evidence level: {top or "none"}).'), []


def study_table(st_df: pd.DataFrame):
    t = st_df.copy()
    t['pubmed'] = t['pmid'].map(PUBMED.format)

    def names(s, empty):
        return ', '.join(atlas.country_name(i) for i in s.split(';') if i) or empty
    t['study_countries'] = t['study_countries'].map(lambda s: names(s, 'Not indexed'))
    t['team_countries'] = t['team_countries'].map(lambda s: names(s, '—'))
    st.dataframe(
        t.sort_values('year', ascending=False)[
            ['year', 'title', 'ancestry', 'study_countries', 'team_countries', 'design',
             'participants', 'best_level', 'pubmed']],
        hide_index=True, width='stretch', column_config={
            'year': st.column_config.NumberColumn('Year', format='%d'), 'title': 'Study',
            'ancestry': 'Ancestry of participants', 'study_countries': 'Done in',
            'team_countries': 'Research team in', 'design': 'Design',
            'participants': st.column_config.NumberColumn('Participants', format='%d'),
            'best_level': st.column_config.TextColumn(
                'ClinPGx level', help='1A strongest … 4 weakest'),
            'pubmed': st.column_config.LinkColumn('PubMed', display_text='Open')})


SEARCH_DIR = atlas.LIVE_DIR.parent / 'searches'


def latest_search(drug: str):
    """Most recent saved wider search for a medicine, or None."""
    slug = ''.join(c if c.isalnum() else '-' for c in drug).strip('-')
    hits = sorted(SEARCH_DIR.glob(f'{slug}_*/report.json'), reverse=True)
    if not hits:
        return None, None
    return json.loads(hits[0].read_text('utf-8')), hits[0].parent


def literature_tab(drug):
    import pandas as pd
    st.markdown('### Search beyond ClinPGx')
    st.markdown('<p class="hra-note">Searches PubMed, Europe PMC and ClinicalTrials.gov for this medicine '
                '(including its synonyms and brand names from ChEMBL), removes duplicates across databases, '
                'and classifies the evidence with written rules. Needs an internet connection and takes '
                'a few minutes for well-studied medicines. Extracted details are marked unverified until checked against the '
                'publication.</p>', unsafe_allow_html=True)
    if not drug:
        st.info('Choose a medicine at the top of the page first.')
        return
    rep, folder = latest_search(drug)
    label = 'Search again' if rep else f'Search the literature for {drug}'
    if st.button(label, type='primary', key='lit_go'):
        from hra.engine import search_medicine
        with st.status(f'Searching for {drug}…', expanded=True) as status:
            try:
                res = search_medicine(drug, clinpgx_data=data, log=st.write)
                folder = res.write_report(SEARCH_DIR)
                rep = res.report
                status.update(label='Search finished.', state='complete')
            except Exception as e:     # never silently show an empty result
                status.update(label='Search could not run.', state='error')
                st.error(f'{e}')
                return
    if not rep:
        return
    st.caption(f"Searched {rep['finished_at'][:16].replace('T', ' ')} UTC · engine v{rep['engine_version']} · "
               f"names used: {', '.join(rep['search_names'])}")
    srcs = pd.DataFrame(rep['sources'])[['source', 'status', 'records_retrieved', 'total_hits_reported',
                                         'truncated', 'error']]
    bad = srcs[srcs.status != 'searched']
    if len(bad):
        st.warning('Not every source could be searched: ' + ', '.join(
            f"{r.source} ({r.status}{': ' + r.error if r.error else ''})" for r in bad.itertuples())
            + '. Results are incomplete, and nothing here should be read as "no research exists".')
    st.dataframe(srcs, hide_index=True, width='stretch', column_config={
        'source': 'Source', 'status': 'Status', 'records_retrieved': 'Records retrieved',
        'total_hits_reported': 'Hits reported', 'truncated': 'More hits than retrieved', 'error': 'Error'})
    t = rep['totals']
    k = st.columns(3)
    k[0].metric('Records retrieved', f"{t['records_retrieved']:,}")
    k[1].metric('Unique studies', f"{t['unique_studies']:,}", help='After removing duplicates across databases.')
    k[2].metric('Genes with established evidence',
                sum(g['category'] == 'Established evidence' for g in rep['genes']))
    st.markdown('#### Evidence classification')
    st.dataframe(pd.DataFrame([{'Evidence type': c, **v} for c, v in rep['evidence_categories'].items()])[
        ['Evidence type', 'category', 'method', 'unique_studies', 'reason', 'partial_search']],
        hide_index=True, width='stretch', column_config={'category': 'Classification', 'method': 'Method',
                                                         'unique_studies': 'Relevant studies',
                                                         'reason': 'Why', 'partial_search': 'Partial search'})
    st.caption(f"Rules: {rep.get('classification_rules_version', 'v1')}. Efficacy and safety are never "
               'classed as established from study counts; a person must review the findings first.')
    if rep['genes']:
        gdf = pd.DataFrame([{**g, 'evidence': '; '.join(f"{c['type']} {c['id']}" for c in g.get('supporting', [])[:3]),
                             'link': next((c['url'] for c in g.get('supporting', []) if c.get('url')), None)}
                            for g in rep['genes']])
        st.dataframe(gdf[['gene', 'category', 'reason', 'evidence', 'link']],
                     hide_index=True, width='stretch', column_config={
                         'gene': 'Gene', 'category': 'Classification', 'reason': 'Why',
                         'evidence': 'Supporting evidence',
                         'link': st.column_config.LinkColumn('Source', display_text='Open')})
    integ = rep.get('integrity')
    if integ:
        if integ['problems']:
            st.error(f"Evidence check: {len(integ['problems'])} claims lack traceable support. "
                     + '; '.join(integ['problems'][:3]))
        else:
            st.success(f"Evidence check passed: all {integ['checked_claims']:,} claims in this report trace "
                       'to identifiable studies, annotations or guidelines.')
    titles = {
        'curated_ancestry_groups (ClinPGx, curator-reviewed)': ('Ancestry groups (ClinPGx curators)', 'Studies'),
        'registry_race_ethnicity_participants (ClinicalTrials.gov results, registry categories)':
            ('Race / ethnicity reported in trial results (registry wording)', 'Participants'),
        'stated_population_descriptions (rule-extracted, unverified)':
            ('Populations described in abstracts (unverified)', 'Studies'),
        '1_registered_trial_sites (registry)': ('1. Registered trial sites', 'Studies'),
        '1b_recruitment_country_stated_in_abstract (rule-extracted, unverified)':
            ('1b. Recruitment country stated in abstract (unverified)', 'Studies'),
        '2_author_affiliations': ('2. Author locations', 'Studies'),
        '3_populations_described_in_reports': ('3. Populations described in reports', 'Studies'),
        '3b_place_indexed_by_pubmed (not proof of recruitment)':
            ('3b. Place indexed by PubMed (not proof of recruitment)', 'Studies'),
    }

    def show_layer(name, val):
        title, unit = titles.get(name, (name, 'Count'))
        st.markdown(f'**{title}**')
        if isinstance(val, dict):
            if val:
                rows = [{'': k, unit: v['count'] if isinstance(v, dict) else v,
                         'Evidence': ', '.join(v['evidence'][:6]) + (f" +{len(v['evidence']) - 6} more"
                                                                    if len(v['evidence']) > 6 else '')
                         if isinstance(v, dict) else ''} for k, v in val.items()]
                st.dataframe(pd.DataFrame(rows).head(15), hide_index=True, width='stretch',
                             column_config={'Evidence': st.column_config.TextColumn(
                                 'Supporting studies', help='Study keys: pmid:… is a PubMed ID, '
                                                            'nct:… a ClinicalTrials.gov ID.')})
            else:
                st.caption('None recorded in the searched sources.')
        else:
            st.caption(f'{val:,}')
    c1, c2 = st.columns(2, gap='large')
    with c1:
        st.markdown('#### Who took part')
        pop = rep['population']
        st.caption(f"{pop['studies_with_any_population_information']:,} studies say who took part; "
                   f"{pop['studies_without_population_information']:,} do not.")
        for name, val in pop.items():
            if not name.startswith('studies_'):
                show_layer(name, val)
    with c2:
        st.markdown('#### Where (four separate layers)')
        g = rep['geography']
        st.caption(f"{g['4_studies_with_no_geographic_information']:,} studies have no geographic "
                   'information in any layer.')
        for name, val in g.items():
            if not name.startswith('4_'):
                show_layer(name, val)
    if rep['unresolved_questions']:
        st.markdown('#### Unresolved questions')
        st.markdown('\n'.join(f'- {q}' for q in rep['unresolved_questions']))
    studies = pd.read_csv(folder / 'studies.csv', dtype=str, keep_default_na=False) \
        if (folder / 'studies.csv').exists() and (folder / 'studies.csv').stat().st_size else pd.DataFrame()
    if len(studies):
        studies['link'] = studies.source_links.str.split(' ').str[0]
        with st.expander(f'All {len(studies):,} unique studies'):
            st.dataframe(studies[['year', 'title', 'found_in', 'categories', 'pmids', 'nct_ids', 'link']],
                         hide_index=True, width='stretch', column_config={
                             'year': 'Year', 'title': 'Study', 'found_in': 'Found in',
                             'categories': 'Evidence type', 'pmids': 'PMID', 'nct_ids': 'Trial ID',
                             'link': st.column_config.LinkColumn('Open', display_text='Open')})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(folder.glob('*')):
            zf.write(f, f.name)
        zf.writestr('ATTRIBUTION_AND_LICENCE.txt', atlas.attribution_text(manifest))
    st.download_button('Download the evidence-gap report (HTML, JSON, CSV)', buf.getvalue(),
                       file_name=f'{folder.name}_evidence_gap_report.zip', mime='application/zip')


def ask_page():
    st.markdown('<p class="hra-finding">Will this medicine work for me?</p>'
                '<p class="hra-sub">No database can answer that for one person. This page tells you '
                'what research says about people like you, and how much research there is. Your '
                'answers are not saved.</p>', unsafe_allow_html=True)
    drugs = sorted(assoc.drug.unique())
    c1, c2 = st.columns([1, 1], gap='large')
    drug = c1.selectbox('Which medicine?', drugs, index=None, key='ask_drug',
                        placeholder='Start typing a medicine name',
                        format_func=str.capitalize,
                        help='Use the medicine’s generic name, for example clopidogrel rather than '
                             'Plavix. Only medicines with genetic research in ClinPGx are listed.')
    groups = c2.multiselect('Which groups describe your family’s ancestry?', list(ANCESTRY_CHOICES),
                            key='ask_groups', format_func=lambda g: ANCESTRY_CHOICES[g],
                            placeholder='Choose one or more, or leave blank',
                            help='These are the groups researchers use. Choose all that apply. '
                                 'Leave it blank if you are not sure or would rather not say.')
    countries = sorted(geo.country_table().items(), key=lambda kv: kv[1]['name'])
    home = c1.selectbox('Where do you live? (optional)', [c for c, _ in countries], index=None,
                        key='ask_country', placeholder='Choose a country',
                        format_func=lambda i: geo.country_table()[i]['name'])

    if not drug:
        st.markdown('<div class="hra-empty"><p>Choose a medicine to see what research says. '
                    'For example, try <b>clopidogrel</b>, a heart medicine whose effect depends on a '
                    'gene called CYP2C19.</p></div>', unsafe_allow_html=True)
        return

    sdf = _studies(stamp, drug, None)
    anc = _ancestry(stamp, drug, None, min_studies, min_participants)
    summ = atlas.location_gaps_summary(sdf)
    total = summ['studies']
    card1, ask_genes = gene_answer(drug)

    # Card 2: people like you
    real = anc[~anc.status.eq('Not a population group')].sort_values('studies', ascending=False)
    best = real.iloc[0] if len(real) and real.iloc[0].studies else None
    tone = {'Available': 'good', 'Limited': 'warn', 'Missing': 'none'}
    if groups:
        rows = real.set_index('ancestry')
        lines, worst = [], 'Available'
        best_n = int(best.studies) if best is not None else 0
        for g in groups:
            n = int(rows.loc[g, 'studies']) if g in rows.index else 0
            # judged against the best-studied group, so a handful of studies isn't called "available"
            status = ('Missing' if n == 0 else
                      'Available' if n >= min_studies and n >= 0.25 * best_n else 'Limited')
            if ['Available', 'Limited', 'Missing'].index(status) > \
                    ['Available', 'Limited', 'Missing'].index(worst):
                worst = status
            name = ANCESTRY_CHOICES[g].split(':')[0]
            lines.append(f'<b>{n:,} of {total:,}</b> included people of {name} ancestry.'
                         if n else f'<b>None of the {total:,}</b> included people of {name} ancestry.')
        compare = ''
        if best is not None and best.ancestry not in groups:
            compare = (f'For comparison, {int(best.studies):,} included people of '
                       f'{ANCESTRY_CHOICES[best.ancestry].split(":")[0]} ancestry.')
        card2 = _card('Have people like you been studied?', _tag(LABEL[worst], tone[worst]),
                      f'ClinPGx lists {plural(total, "study")} on genes and {drug}. '
                      + ' '.join(lines), compare)
    else:
        thin = real[real.status.isin(['Limited', 'Missing'])].ancestry.map(
            lambda g: ANCESTRY_CHOICES[g].split(':')[0]).tolist()
        card2 = _card('Who has been studied?', _tag('Choose your ancestry above', 'info'),
                      f'ClinPGx lists {plural(total, "study")} on genes and {drug}.'
                      + (f' Most included people of {ANCESTRY_CHOICES[best.ancestry].split(":")[0]} '
                         f'ancestry ({int(best.studies):,}).' if best is not None else ''),
                      (f'Little or no research on: {_join(thin)}.' if thin else ''))

    # Card 3: where the research was done
    cov = _countries(stamp, drug, None, 'study location', min_studies, min_participants)
    top3 = cov[cov.studies > 0].nlargest(3, 'studies')
    share = summ['with_study_location'] / total if total else 0
    where = (f'Most located studies were done in {_join(top3.country.tolist())}.'
             if len(top3) else 'None of these studies has a recorded country.')
    if home:
        n_home = int(cov.set_index('iso3').loc[home, 'studies']) if home in set(cov.iso3) else 0
        hname = geo.country_table()[home]['name']
        status3 = _tag(f'{n_home} in {hname}', 'good' if n_home >= min_studies else
                       ('warn' if n_home else 'none'))
        body3 = (f'{plural(n_home, "study")} {"was" if n_home == 1 else "were"} done in {hname}. '
                 if n_home else f'No study is recorded as done in {hname}. ') + where
    else:
        status3, body3 = _tag('Country not given', 'info'), where
    card3 = _card('Where was the research done?', status3, body3,
                  (f'PubMed records a country for only {share:.0%} of these studies, so this is a '
                   'minimum.') if share else 'PubMed records no country for these studies.')

    st.markdown(f'<div class="hra-answers">{card1}{card2}{card3}</div>', unsafe_allow_html=True)
    # Every number above can be checked: list the exact studies behind it.
    with st.expander('See the studies behind these numbers'):
        shown = False
        for g in groups:
            name = ANCESTRY_CHOICES[g].split(':')[0]
            these = sdf[sdf.ancestry.str.split(';').map(lambda xs: g in xs)]
            if len(these):
                st.markdown(f'**{len(these):,} {"study" if len(these) == 1 else "studies"} that included people of '
                            f'{name} ancestry** (ancestry as recorded by ClinPGx curators)')
                study_table(these)
                shown = True
        if home:
            here_ = sdf[sdf.study_countries.str.split(';').map(lambda xs: home in xs)]
            if len(here_):
                st.markdown(f'**{len(here_):,} done in {geo.country_table()[home]["name"]}** '
                            '(country from PubMed indexing)')
                study_table(here_)
                shown = True
        if not shown:
            st.markdown(f'**All {len(sdf):,} studies on genes and {drug} in ClinPGx**')
            study_table(sdf)
    wider, _ = latest_search(drug)
    if wider:
        ok = [x['source'] for x in wider['sources'] if x['status'] == 'searched'
              and x['source'] in ('pubmed', 'europepmc', 'clinicaltrials')]
        names = {'pubmed': 'PubMed', 'europepmc': 'Europe PMC', 'clinicaltrials': 'ClinicalTrials.gov'}
        described = wider['population']['studies_with_any_population_information']
        st.markdown(
            f'<p class="hra-note">A wider search on {wider["finished_at"][:10]} of '
            f'{_join([names[x] for x in ok]) if ok else "other databases"} found '
            f'{wider["totals"]["unique_studies"]:,} studies of {drug} in total. {described:,} of them '
            'say something about who took part; most of those details have not yet been checked by a '
            'person.</p>', unsafe_allow_html=True)

    steps = [f'This cannot tell you whether {drug} will work for you. People within any group '
             'differ, and the evidence about a group cannot predict one person’s response.',
             'Do not stop, start or change a medicine without talking to your doctor or pharmacist.']
    if ask_genes:
        steps.append(f'You could ask your doctor or pharmacist whether a genetic test for '
                     f'{_join(ask_genes)} is relevant for you.')
    if groups and best is not None:
        steps.append('If people like you are under-studied, that is a gap in research, not a sign '
                     'that the medicine is unsafe for you.')
    st.markdown('<div class="hra-means"><h3>What this means for you</h3><ul>'
                + ''.join(f'<li>{s}</li>' for s in steps) + '</ul></div>', unsafe_allow_html=True)
    st.button(f'See the full evidence for {drug}', on_click=_go_explore, args=(drug,))

st.markdown(f'<div class="hra-brand"><b>Human Response Atlas</b><span>'
            f'{atlas.release_label(manifest)} · downloaded {manifest["accessed_utc"][:10]}</span></div>',
            unsafe_allow_html=True)

ASK, EXPLORE = 'Will this medicine work for me?', 'Explore the evidence'
mode = st.radio('View', [ASK, EXPLORE], horizontal=True, key='mode',
                label_visibility='collapsed')

if mode == ASK:
    ask_page()
    footer()
    st.stop()

# ---- Filters (apply to every tab) ------------------------------------------
f1, f2, f3 = st.columns([2, 2, 3])
drug = f1.selectbox('Medicine', [ALL_MEDS] + sorted(assoc.drug.unique()), key='x_drug',
                    format_func=lambda d: d if d == ALL_MEDS else d.capitalize(),
                    help='Start typing to search.')
drug = None if drug == ALL_MEDS else drug
if drug:
    gene = f2.selectbox('Gene', [ALL_GENES] + atlas.annotations_for(data, drug)['gene']
                        .drop_duplicates().tolist())
    gene = None if gene == ALL_GENES else gene
else:
    f2.selectbox('Gene', [ALL_GENES], disabled=True, help='Choose a medicine first.')
    gene = None
basis_label = f3.radio('Place studies by', ['Where the study was done',
                                            'Where the research team is based'],
                       horizontal=True, key='basis')
basis = 'study location' if basis_label.startswith('Where the study') else 'research team'

sdf = _studies(stamp, drug, gene)
cov = _countries(stamp, drug, gene, basis, min_studies, min_participants)
anc = _ancestry(stamp, drug, gene, min_studies, min_participants)
summ = atlas.location_gaps_summary(sdf)

# ---- Headline finding --------------------------------------------------------
subject = (f'{drug} and {gene}' if gene else drug) if drug else 'pharmacogenomics'
n_c, n_all = int((cov.studies > 0).sum()), len(cov)
verb = 'were done in at least' if basis == 'study location' else 'came from research teams in at least'
placed = summ['with_study_location'] if basis == 'study location' else summ['with_team_location']
if summ['studies'] == 0:
    finding = f'ClinPGx has no annotated studies for {subject} yet.'
    sub = 'Try another medicine or gene, or choose “All medicines”.'
else:
    if n_c:
        finding = (f'The {plural(summ["studies"], "study")} behind ClinPGx’s evidence on {subject} '
                   f'{verb} {n_c} of {n_all} countries.')
    else:
        finding = (f'ClinPGx’s evidence on {subject} rests on {plural(summ["studies"], "study")}, '
                   'none with a recorded country.')
    groups = anc[~anc.status.eq('Not a population group')]
    specific = sdf.ancestry.str.split(';').map(
        lambda g: set(g) - atlas.NON_GROUP_LABELS - {'Not recorded'})
    specific = specific[specific.map(bool)]
    eur = specific.map(lambda g: 'European' in g).mean() if len(specific) else 0
    weak = groups[groups.status.isin(['Limited', 'Missing'])]
    where = ('PubMed records a country for' if basis == 'study location'
             else 'Author addresses identify a country for')
    sub = (f'{where} {placed / summ["studies"]:.0%} of these studies. '
           + (f'Of the studies that name an ancestry group, {eur:.0%} included people of European '
              'ancestry. ' if len(specific) else '')
           + f'{len(weak)} of {len(groups)} ancestry groups '
           + ('has' if len(weak) == 1 else 'have') + ' limited or no evidence'
           + (f': {", ".join(weak.ancestry.head(4))}{" and others" if len(weak) > 4 else ""}.'
              if len(weak) else '.'))
st.markdown(f'<p class="hra-finding">{finding}</p><p class="hra-sub">{sub}</p>',
            unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def _alphagenome(stamp):
    return alphagenome_atlas.load()


def alphagenome_section(anns):
    """AI predictions for the variants of this medicine. Shown for exploration only; never used to
    classify evidence and never shown on the "Will this medicine work for me?" page."""
    st.markdown('#### AI-predicted effect of these DNA changes (AlphaGenome)')
    f = alphagenome_atlas.SUMMARY_FILE
    summ, man = _alphagenome(f.stat().st_mtime if f.exists() else 0)
    rs = anns[anns.variant.astype(str).str.match(r'^rs\d+$')]
    if summ is None:
        st.caption('Predictions from Google DeepMind’s AlphaGenome Atlas have not been downloaded on this '
                   'computer. See “AlphaGenome predictions” in the README to add them.')
        return
    if rs.empty:
        st.caption('This evidence names gene variants as star alleles or haplotypes (combinations of DNA '
                   'changes), which AlphaGenome does not score one by one.')
        return
    best = rs.groupby(['gene', 'variant'], as_index=False).level_of_evidence.min()
    t = best.merge(summ, left_on='variant', right_on='rsid', how='left', suffixes=('', '_dna'))
    n_rs, n_scored = best.variant.nunique(), t.dropna(subset=['max_score']).variant.nunique()
    st.markdown(f'<p class="hra-note">{n_scored} of {plural(n_rs, "single DNA change")} named in this evidence '
                'have a prediction. A score near 1 means AlphaGenome predicts a larger effect on gene '
                'activity than almost all common human variants, in at least one tissue or cell type. It '
                'is not evidence that the change affects this medicine.</p>', unsafe_allow_html=True)
    t = t.sort_values('max_score', ascending=False, na_position='last')
    st.dataframe(t[['gene', 'variant', 'variant_dna', 'max_score', 'scorer', 'where', 'level_of_evidence']],
                 hide_index=True, width='stretch', column_config={
                     'gene': 'Gene', 'variant': 'Variant',
                     'variant_dna': st.column_config.TextColumn('DNA change (GRCh38)'),
                     'max_score': st.column_config.ProgressColumn(
                         'Strongest predicted effect', min_value=0, max_value=1, format='%.2f',
                         help='AlphaGenome’s calibrated score (quantile against common variants), the '
                              'largest across all prediction types, tissues and genes. Blank: no prediction.'),
                     'scorer': st.column_config.TextColumn('Prediction type', help='Which kind of gene '
                                                           'activity the strongest effect is on.'),
                     'where': 'Tissue or cell type', 'level_of_evidence': 'ClinPGx level'})
    st.caption(alphagenome_atlas.DISCLAIMER + ' ' + alphagenome_atlas.TERMS_NOTICE
               + (f" Retrieved {man['retrieved_utc'][:10]}." if man and man.get('retrieved_utc') else ''))


tab_map, tab_people, tab_med, tab_lit, tab_help = st.tabs(
    ['World map', 'Who was studied', 'Medicine details', 'Expand evidence search', 'How to read this'])


# ---- helpers -----------------------------------------------------------------
def world_map(cov: pd.DataFrame):
    c = cov.copy()
    c['label'] = c['status'].map(LABEL)
    c['participants_label'] = c['participants'].map(
        lambda v: 'not reported' if pd.isna(v) else f'{int(v):,}')
    c.loc[c.studies == 0, 'participants_label'] = '0'
    fields = ['country', 'label', 'studies', 'participants_label', 'best_level',
              'ancestry_of_participants', 'latest_year']
    base = alt.Chart(alt.Data(values=GEO['features'])).transform_calculate(
        iso3='datum.properties.iso3').transform_lookup(
        lookup='iso3', from_=alt.LookupData(c, 'iso3', fields))
    pick = alt.selection_point(fields=['iso3'], name='country', on='click', empty=False)
    if shade == 'Evidence level':
        colour = alt.Color('label:N', legend=None, scale=alt.Scale(
            domain=[v[0] for v in STATUS.values()], range=[v[1] for v in STATUS.values()]))
    else:
        colour = alt.condition('datum.studies > 0', alt.Color(
            'studies:Q', title='Studies', scale=alt.Scale(type='log', range=['#cfe5e3', TEAL]),
            legend=alt.Legend(orient='bottom')), alt.value(BLANK))
    chart = base.mark_geoshape(stroke='#ffffff', strokeWidth=0.5).encode(
        color=colour,
        stroke=alt.condition(pick, alt.value(INK), alt.value('#ffffff')),
        strokeWidth=alt.condition(pick, alt.value(1.8), alt.value(0.5)),
        tooltip=[alt.Tooltip('country:N', title='Country'), alt.Tooltip('label:N', title='Evidence'),
                 alt.Tooltip('studies:Q', title='Studies'),
                 alt.Tooltip('participants_label:N', title='Participants'),
                 alt.Tooltip('ancestry_of_participants:N', title='Ancestry of participants')],
    ).add_params(pick).project('equalEarth').properties(height=460).configure_view(stroke=None)
    return st.altair_chart(chart, width='stretch', on_select='rerun', key='worldmap')


def export_zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, df in files.items():
            zf.writestr(name, df.to_csv(index=False))
        zf.writestr('ATTRIBUTION_AND_LICENCE.txt', atlas.attribution_text(manifest))
        for f in sorted((atlas.LIVE_DIR / 'upstream_licences').glob('*')):
            zf.writestr(f'upstream_licences/{f.name}', f.read_text('utf-8', errors='replace'))
        zf.writestr('upstream_licences/natural_earth.md',
                    (geo.GEO_DIR / 'NATURAL_EARTH_LICENSE.md').read_text('utf-8'))
    return buf.getvalue()


def facts(rows: list[tuple[str, str]]) -> str:
    return '<dl class="hra-facts">' + ''.join(f'<dt>{a}</dt><dd>{b}</dd>' for a, b in rows) + '</dl>'


def fmt_people(v) -> str:
    return 'not reported' if pd.isna(v) else f'{int(v):,}'


# ---- World map -----------------------------------------------------------------
with tab_map:
    left, right = st.columns([2.3, 1], gap='large')
    with left:
        event = world_map(cov)
        if shade == 'Evidence level':
            st.markdown(key_legend(), unsafe_allow_html=True)
        off = summ['studies'] - (summ['with_study_location'] if basis == 'study location'
                                 else summ['with_team_location'])
        st.markdown(
            f'<p class="hra-note">Grey land has no studies in this snapshot — that is not proof '
            f'none exist. {plural(off, "study")} could not be placed on the map'
            + (f' ({summ["not_yet_indexed"]:,} not yet indexed by PubMed, '
               f'{summ["region_only"]:,} tagged only with a region).' if basis == 'study location'
               else ' (author addresses not recognised).')
            + ' A study run in several countries counts in each.</p>', unsafe_allow_html=True)

    picked = None
    try:
        sel = event.selection['country']
        picked = sel[0]['iso3'] if sel else None
    except Exception:
        pass
    here = sdf.iloc[0:0]
    with right:
        if picked and picked in set(cov.iso3):
            row = cov.set_index('iso3').loc[picked]
            col = 'study_countries' if basis == 'study location' else 'team_countries'
            here = sdf[sdf[col].str.split(';').map(lambda xs: picked in xs)]
            st.markdown(f'### {row["country"]}\n{pill(row["status"])}', unsafe_allow_html=True)
            if row['studies']:
                st.markdown(facts([
                    ('Studies', f"{int(row['studies']):,}"),
                    ('Participants (approx.)', fmt_people(row['participants'])),
                    ('Strongest ClinPGx level', row['best_level'] or '—'),
                    ('Trials or meta-analyses', f"{int(row['trials_or_meta'])}"),
                    ('Most recent study', f"{int(row['latest_year'])}" if pd.notna(row['latest_year'])
                     else '—'),
                    ('Quality signal', row['quality_signal'] or '—'),
                ]), unsafe_allow_html=True)
                st.markdown(f'<p class="hra-note"><b>Ancestry of participants:</b> '
                            f'{row["ancestry_of_participants"] or "not recorded"}</p>',
                            unsafe_allow_html=True)
            else:
                st.markdown('<p class="hra-note">No studies in this snapshot were '
                            + ('done here.' if basis == 'study location' else 'led from here.')
                            + '</p>', unsafe_allow_html=True)
        else:
            st.markdown('#### Countries with the most studies')
            top = cov[cov.studies > 0].nlargest(10, 'studies')
            if len(top):
                top = top.assign(label=top.status.map(LABEL))
                st.altair_chart(alt.Chart(top).mark_bar(cornerRadiusEnd=2).encode(
                    y=alt.Y('country:N', sort='-x', title=None, axis=alt.Axis(labelLimit=150)),
                    x=alt.X('studies:Q', title=None, axis=alt.Axis(tickMinStep=1, format='d')),
                    color=alt.Color('label:N', legend=None, scale=alt.Scale(
                        domain=[v[0] for v in STATUS.values()],
                        range=[v[1] for v in STATUS.values()])),
                    tooltip=['country', 'studies']).properties(height=alt.Step(24)),
                    width='stretch')
            st.markdown('<p class="hra-note">Click a country on the map to see its studies.</p>',
                        unsafe_allow_html=True)

    if len(here):
        with st.expander(f'Studies {"done in" if basis == "study location" else "led from"} '
                         f'{atlas.country_name(picked)} ({len(here)})', expanded=True):
            study_table(here)
    with st.expander('Show the full country table'):
        show = cov[cov.studies > 0].assign(evidence=lambda d: d.status.map(LABEL)).sort_values(
            'studies', ascending=False)
        st.dataframe(show[['country', 'evidence', 'studies', 'participants', 'best_level',
                           'trials_or_meta', 'latest_year', 'quality_signal',
                           'ancestry_of_participants']], hide_index=True, width='stretch',
                     column_config={'country': 'Country', 'evidence': 'Evidence',
                                    'studies': 'Studies',
                                    'participants': st.column_config.NumberColumn(
                                        'Participants', format='%d'),
                                    'best_level': 'Strongest level',
                                    'trials_or_meta': 'Trials / meta-analyses',
                                    'latest_year': st.column_config.NumberColumn(
                                        'Most recent', format='%d'),
                                    'quality_signal': 'Quality signal',
                                    'ancestry_of_participants': 'Ancestry of participants'})
    st.download_button('Download this map’s data', export_zip(
        {f'countries_by_{basis.replace(" ", "_")}.csv': cov, 'studies.csv': sdf}),
        file_name=f"human_response_atlas_map_{drug or 'all'}_{gene or 'all'}.zip",
        mime='application/zip', help='A ZIP with the tables and the required attribution.')

# ---- Who was studied ---------------------------------------------------------
with tab_people:
    groups = anc[~anc.status.eq('Not a population group')].copy()
    groups['label'] = groups.status.map(LABEL)
    groups['text'] = groups.studies.map(lambda n: plural(n, 'study') if n else 'none')
    st.markdown('### Studies by ancestry of participants')
    st.markdown('<p class="hra-note">Ancestry groups as recorded by ClinPGx. These describe people, '
                'not places — the grid below shows where each group was studied.</p>',
                unsafe_allow_html=True)
    order = groups.sort_values('studies', ascending=False)['ancestry'].tolist()
    base = alt.Chart(groups).encode(
        y=alt.Y('ancestry:N', sort=order, title=None, axis=alt.Axis(labelLimit=320, labelFontSize=13)),
        x=alt.X('studies:Q', title=None, axis=alt.Axis(tickMinStep=1, format='d', grid=False)),
        tooltip=[alt.Tooltip('ancestry:N', title='Ancestry'), alt.Tooltip('label:N', title='Evidence'),
                 alt.Tooltip('studies:Q', title='Studies'),
                 alt.Tooltip('studied_in:N', title='Studied in')])
    st.altair_chart(alt.layer(
        base.mark_bar(cornerRadiusEnd=2).encode(color=alt.Color('label:N', legend=None, scale=alt.Scale(
            domain=[v[0] for v in STATUS.values()], range=[v[1] for v in STATUS.values()]))),
        base.mark_text(align='left', dx=6, color=MUTED, fontSize=12).encode(text='text:N'),
    ).properties(height=alt.Step(34)).configure_view(stroke=None), width='stretch')
    st.markdown(key_legend(), unsafe_allow_html=True)

    st.markdown('### Where each ancestry group was studied')
    mx = atlas.ancestry_by_location(sdf)
    if mx.empty:
        st.info('No studies for this selection.')
    else:
        col_order = (mx.groupby('study_countries')['studies'].sum().sort_values(ascending=False)
                     .index.tolist())
        col_order = [c for c in col_order if c not in ('Not indexed', 'Other countries')] + \
            [c for c in ('Other countries', 'Not indexed') if c in col_order]
        row_order = mx.groupby('ancestry')['studies'].sum().sort_values(ascending=False).index.tolist()
        heat = alt.Chart(mx).mark_rect(cornerRadius=2).encode(
            x=alt.X('study_countries:N', title=None, sort=col_order,
                    axis=alt.Axis(labelAngle=-40, labelLimit=150, orient='top', labelOverlap=False,
                                  labelAlign='left')),
            y=alt.Y('ancestry:N', title=None, sort=row_order, axis=alt.Axis(labelLimit=260)),
            color=alt.Color('studies:Q', legend=None,
                            scale=alt.Scale(type='log', range=['#d6ebe9', TEAL])),
            tooltip=[alt.Tooltip('ancestry:N', title='Ancestry'),
                     alt.Tooltip('study_countries:N', title='Done in'),
                     alt.Tooltip('studies:Q', title='Studies')])
        text = alt.Chart(mx).mark_text(fontSize=11).encode(
            x=alt.X('study_countries:N', sort=col_order), y=alt.Y('ancestry:N', sort=row_order),
            text='studies:Q',
            color=alt.condition('datum.studies >= 10', alt.value('#ffffff'), alt.value(INK)))
        st.altair_chart(alt.layer(heat, text).properties(height=alt.Step(30))
                        .configure_view(stroke=None), width='stretch')
        st.markdown('<p class="hra-note">Each number counts studies of one ancestry group done in '
                    'one country. “Not indexed” means PubMed gives no country for the study.</p>',
                    unsafe_allow_html=True)
    with st.expander('Show the evidence-quality table'):
        st.dataframe(anc.assign(evidence=anc.status.map(LABEL).fillna(anc.status))[
            ['ancestry', 'evidence', 'studies', 'participants', 'best_level', 'studies_high_level',
             'trials_or_meta', 'observational', 'latest_year', 'pct_significant', 'quality_signal',
             'studied_in']], hide_index=True, width='stretch', column_config={
            'ancestry': 'Ancestry', 'evidence': 'Evidence', 'studies': 'Studies',
            'participants': st.column_config.NumberColumn('Participants', format='%d'),
            'best_level': 'Strongest level', 'studies_high_level': 'Studies at level 1A–2B',
            'trials_or_meta': 'Trials / meta-analyses', 'observational': 'Observational',
            'latest_year': st.column_config.NumberColumn('Most recent', format='%d'),
            'pct_significant': st.column_config.NumberColumn('% significant', format='%d%%'),
            'quality_signal': 'Quality signal', 'studied_in': 'Studied in'})
    st.download_button('Download this view’s data', export_zip(
        {'ancestry.csv': anc, 'ancestry_by_country.csv': mx, 'studies.csv': sdf}),
        file_name=f"human_response_atlas_ancestry_{drug or 'all'}_{gene or 'all'}.zip",
        mime='application/zip')

# ---- Medicine details --------------------------------------------------------
with tab_med:
    if not drug:
        st.markdown('<div class="hra-empty"><p>Choose a medicine in the box above to see its '
                    'CPIC guideline, the ClinPGx evidence and the studies behind it.</p></div>',
                    unsafe_allow_html=True)
    else:
        cpic = atlas.cpic_for(data, drug, gene)
        anns = atlas.annotations_for(data, drug, gene)
        st.markdown(f'### {drug.capitalize()}' + (f' and {gene}' if gene else ''))
        if len(cpic):
            for _, r in cpic.iterrows():
                pmids = [p for p in r.cpic_pmids.split(';') if p]
                link = (f'[{r.cpic_guideline}]({r.cpic_guideline_url})' if r.cpic_guideline
                        else 'No published CPIC guideline yet')
                st.markdown(f'**{r.gene}**: CPIC level **{r.cpic_level}**. {link}'
                            + ('. Guideline papers: ' + ', '.join(
                                f'[{p}]({PUBMED.format(p)})' for p in pmids) if pmids else ''))
        else:
            st.markdown('CPIC does not list this medicine' + (' with this gene.' if gene else '.'))
        st.markdown('#### ClinPGx evidence')
        st.dataframe(anns[['gene', 'variant', 'level_of_evidence', 'outcome', 'phenotypes',
                           'pmid_count', 'latest_history_date', 'source_url']],
                     hide_index=True, width='stretch', column_config={
            'gene': 'Gene', 'variant': 'Variant', 'level_of_evidence': st.column_config.TextColumn(
                'Level', help='1A strongest … 4 weakest'),
            'outcome': 'Outcome', 'phenotypes': 'What was affected', 'pmid_count': 'Papers',
            'latest_history_date': 'Last updated',
            'source_url': st.column_config.LinkColumn('ClinPGx', display_text='Open')})
        with st.expander(f'Studies behind this evidence ({len(sdf)})'):
            study_table(sdf)
        alphagenome_section(anns)
        evidence = data['evidence'][data['evidence'].summary_annotation_id.isin(
            anns.summary_annotation_id)]
        st.download_button('Download this medicine’s data', export_zip(
            {'annotations.csv': anns, 'evidence.csv': evidence, 'cpic.csv': cpic,
             'studies.csv': sdf, 'ancestry.csv': anc}),
            file_name=f"human_response_atlas_{drug}_{gene or 'all'}.zip", mime='application/zip')

# ---- How to read this --------------------------------------------------------
with tab_lit:
    literature_tab(drug)

with tab_help:
    st.markdown('### What the Atlas shows')
    st.markdown('Each study counted here is one that ClinPGx curators have annotated as evidence '
                'that a gene affects how people respond to a medicine. The Atlas does not search '
                'the wider literature, so grey land means “no studies in ClinPGx yet”, not “no '
                'research exists”.')
    st.markdown('### AI predictions (AlphaGenome)')
    st.markdown('Under *Medicine details*, the Atlas can show predictions from Google DeepMind’s AlphaGenome '
                'Atlas: how strongly an AI model expects each DNA change to alter gene activity in some tissue '
                'or cell type. These are hypotheses, not evidence. They are shown separately, labelled, never '
                'used to classify evidence, and never shown on the “Will this medicine work for me?” page.')
    st.markdown('### Four things kept apart')
    for name, text in atlas.DIMENSIONS.items():
        st.markdown(f'**{name.capitalize()}.** {text}')
    st.markdown('### Evidence levels')
    st.markdown(
        f'- **{LABEL["Available"]}**: at least {plural(min_studies, "study")} and, where sizes are '
        f'reported, at least {min_participants:,} participants. You can change this in Settings '
        '(the arrow at the top left).\n'
        f'- **{LABEL["Limited"]}**: some studies, but fewer or smaller than that.\n'
        f'- **{LABEL["Missing"]}**: none in the loaded ClinPGx snapshot.')
    st.markdown('### Quality signal')
    st.markdown('A simple rule, not a validated score. **Stronger**: 3 or more studies, at least '
                'one behind ClinPGx evidence at level 1A–2B, and a trial, meta-analysis or 1,000+ '
                'participants. **Moderate**: any one of those. **Weaker**: otherwise.')
    st.markdown('### Sources')
    pm = manifest['sources'].get('pubmed', {})
    st.markdown(
        f"- ClinPGx: {atlas.release_label(manifest)}. {LIC['name']} (as stated in the "
        "licence file shipped with the data). Non-commercial use only; anyone you share derived "
        "data with must first agree to the same licence.\n"
        f"- CPIC: {manifest['sources']['cpic']['pairs']:,} gene–medicine pairs. CC0.\n"
        f"- PubMed: {pm.get('pmids', 0):,} studies looked up. Courtesy of the U.S. National Library "
        'of Medicine.\n'
        '- Country borders: Natural Earth (public domain). For display only; no position is '
        'taken on disputed borders.')

footer()
