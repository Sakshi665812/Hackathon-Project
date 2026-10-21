"""Property-driven interface backed by an owner-curated catalogue; no training or uploads."""
from __future__ import annotations
from dataclasses import asdict
import json
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from .catalog import read_catalog, fingerprint
from .composite_physics import Targets, response_curve
from .config import ROOT
from .inverse_design import optimize

PAGES = ['Design optimizer', 'Option database', 'Scientific methodology']


def show_results(result):
    report, table = result.report, result.table
    st.subheader('Optimization results')
    cols = st.columns(4)
    cols[0].metric('Design settings evaluated', f"{report['evaluated_design_settings']:,}")
    cols[1].metric('Feasible designs', f"{len(table):,}")
    cols[2].metric('Pareto alternatives', int(table.pareto.sum()) if not table.empty else 0)
    cols[3].metric('Search verification', 'Exhaustive' if report['globally_verified'] else 'Sampled')
    st.caption(report['claim'] + ' Verification applies to the discrete search and physical assumptions, not experimental performance.')
    if report['ga_absolute_optimality_gap'] is not None:
        st.caption(f"GA weighted-loss gap to exact optimum: {report['ga_absolute_optimality_gap']:.6g} · "
                   f"GA explored {report['ga_evaluated']:,} material subsets before verification.")
    if table.empty:
        if report['globally_verified']:
            st.warning('No combination satisfies all requirements within the selected catalogue and physical model. Adjust the targets or expand the allowed options.')
        else:
            st.warning('This search found no feasible combination. A longer search or different allowed options may help; infeasibility has not been proved.')
    else:
        st.caption('Ranked by the weighted objective among feasible designs. Lower loss is better. Every listed design passes the property thresholds in all specified mechanical scenarios.')
        columns = ['rank','matrix','fillers','electrode','architecture','filler_volume_pct',
                   'sensitivity_min_per_kpa','baseline_capacitance_pf','nonlinearity_max_pct','cost','loss','pareto','evidence']
        st.dataframe(table[columns].head(200), hide_index=True, width='stretch')
        if len(table)>200:
            st.caption('Showing the top 200; the CSV contains all feasible evaluated designs.')
        shown = table.copy()
        shown['frontier'] = shown.pareto.map({True:'Nondominated',False:'Dominated'})
        st.plotly_chart(px.scatter(shown, x='sensitivity_min_per_kpa', y='cost', color='frontier',
            hover_data=['design_id','matrix','fillers','nonlinearity_max_pct'],
            labels={'sensitivity_min_per_kpa':'Minimum scenario sensitivity (kPa⁻¹)', 'cost':'Estimated cost (catalogue units)'},
            title='Sensitivity–cost trade-offs (Pareto comparison also includes nonlinearity)'), width='stretch')
        top = table.head(100)
        names = {row.design_id:f"#{row['rank']} · {row.matrix} · {row.fillers} · {row.filler_volume_pct:g} vol%" for _,row in top.iterrows()}
        selected = st.selectbox('Inspect a proposed design', top.design_id.tolist(), format_func=names.get)
        design = result.designs[selected]
        targets = Targets(**report['targets'])
        curve = pd.DataFrame(response_curve(design['metrics'], targets))
        chart = go.Figure()
        chart.add_trace(go.Scatter(x=curve.pressure_kpa,y=curve.response_high,name='Soft scenario',line=dict(width=0)))
        chart.add_trace(go.Scatter(x=curve.pressure_kpa,y=curve.response_low,name='Stiff scenario',fill='tonexty',line=dict(width=0),fillcolor='rgba(22,125,141,.18)'))
        chart.add_trace(go.Scatter(x=curve.pressure_kpa,y=curve.response_nominal,name='Intermediate scenario',line=dict(color='#167d8d',width=3)))
        chart.update_layout(xaxis_title='Pressure (kPa)',yaxis_title='Modeled ΔC/C₀',title='Pressure response under explicit mechanical scenarios')
        st.plotly_chart(chart, width='stretch')
        st.caption('Shading spans the specified mechanical scenarios. It is not a confidence interval or a measured response. The intermediate curve uses the geometric mean modulus.')
        st.markdown('**Recipe and evidence**')
        recipe = [{'option_id':key,'name':next(c['name'] for c in design['components'] if c['option_id']==key),
                   'volume_percent':100*value} for key,value in design['volume_fractions'].items()]
        st.dataframe(pd.DataFrame(recipe),hide_index=True)
        st.write(f"Electrode: {next(c['name'] for c in design['components'] if c['role']=='electrode')}. "
                 f"Architecture: {next(c['name'] for c in design['components'] if c['role']=='structure')}. "
                 f"Dielectric thickness: {targets.thickness_um:g} µm; active area: {targets.area_cm2:g} cm².")
        st.dataframe(pd.DataFrame(design['components'])[['name','role','evidence_kind','source','conditions']],hide_index=True)
        st.info('This recipe is a model hypothesis. Test independently fabricated replicates against an unfilled matrix control, record C₀ and loading/unloading curves at matched frequency and temperature, and compare the measured response with the scenario envelope.')
        st.download_button('Download response curve',curve.to_csv(index=False),'response_curve.csv','text/csv')
        st.download_button('Download feasible designs',table.to_csv(index=False),'optimized_designs.csv','text/csv')
    with st.expander('Search convergence and constraint diagnostics'):
        history = result.history
        if not history.empty:
            st.plotly_chart(px.line(history,x='evaluated',y='best_feasible_loss',color='restart',markers=True,
                                   labels={'evaluated':'Unique material subsets evaluated','best_feasible_loss':'Best feasible weighted loss'}),width='stretch')
            st.caption('History records GA evaluations. Exact verification, when enabled, follows the GA. Restarts use consecutive seeds and share the evaluation archive.')
        st.write('Rejection counts may overlap because one design can violate several constraints.')
        st.json(report['rejection_counts'])
        st.json(report)
    bundle = {'report':report,'results':table.to_dict('records'),'designs':result.designs,'history':result.history.astype(object).where(pd.notna(result.history),None).to_dict('records')}
    st.download_button('Download reproducibility report',json.dumps(bundle,indent=2,allow_nan=False),'optimization_report.json','application/json')


def designer(options):
    st.write('Specify the properties you need. SensorForge searches the prefilled material database for feasible compositions and architectures using evolutionary optimization and explicit physical models.')
    names = {row['option_id']:row['name'] for row in options}
    evidence_filter = st.selectbox('Evidence scope', ['All catalogue entries', 'Exclude demonstration entries'])
    available = [row for row in options if evidence_filter=='All catalogue entries' or row['evidence_kind']!='demonstration']
    if not available:
        st.info('The owner has not yet installed experimental catalogue entries. Select all entries to test the clearly labelled demonstration database.')
        return
    with st.expander('Allowed search space', expanded=True):
        st.caption('Choose t options from the k catalogue entries. A recipe contains exactly one matrix, zero or more fillers, one electrode pair, and one architecture.')
        selected=[]
        cols=st.columns(2)
        for i,(role,label) in enumerate([('matrix','Allowed matrices'),('filler','Allowed fillers'),('electrode','Allowed electrodes'),('structure','Allowed architectures')]):
            ids=[row['option_id'] for row in available if row['role']==role]
            selected.extend(cols[i%2].multiselect(label, ids, default=ids, format_func=names.get, key='allowed_'+role))
        st.caption(f"{len(selected)} selected / {len(options)} catalogue options. Empty selections exclude that role; matrix, electrode, and architecture selections are required.")
    filler_count=sum(row['role']=='filler' and row['option_id'] in selected for row in available)
    with st.form('optimization_request'):
        st.markdown('**Desired pressure range and properties**')
        a,b,c=st.columns(3)
        pmin=a.number_input('Minimum pressure (kPa)',min_value=0.,value=0.)
        pmax=b.number_input('Maximum pressure (kPa)',min_value=.001,value=10.)
        sensitivity=c.number_input('Minimum sensitivity (kPa⁻¹)',min_value=.000001,value=.001,format='%.6f')
        c0=a.number_input('Minimum baseline capacitance (pF)',min_value=.001,value=1.)
        nonlinearity=b.number_input('Maximum nonlinearity (% full scale)',min_value=.01,value=5.)
        cost=c.number_input('Maximum cost (catalogue units)',min_value=.01,value=20.)
        area=a.number_input('Active electrode area (cm²)',min_value=.001,value=1.)
        thickness=b.number_input('Dielectric thickness (µm)',min_value=.01,value=100.)
        st.markdown('**Combination limits**')
        mode=st.selectbox('Combination size mode',['Range of constituent counts','Exactly this many constituents','Use all allowed fillers'])
        a,b=st.columns(2)
        minimum=a.number_input('Minimum / exact constituent count',min_value=1,max_value=filler_count+1,value=min(2,filler_count+1),step=1)
        maximum=b.number_input('Maximum constituent count',min_value=1,max_value=filler_count+1,value=min(4,filler_count+1),step=1)
        st.caption('Constituents count the matrix plus fillers. Electrodes and architecture are selected separately. “Use all allowed fillers” combines every selected filler with one allowed matrix at a time.')
        loading_pcts=st.multiselect('Total filler loadings to search (vol%)',[1,2,3,5,7,10],default=[2,5,10])
        st.caption('Fillers share the total filler volume equally. The matrix supplies the remaining volume. Catalogue compatibility and loading limits still apply.')
        with st.expander('Trade-off priorities and search settings'):
            a,b,c=st.columns(3)
            sw=a.number_input('Sensitivity priority',min_value=0.,value=1.)
            lw=b.number_input('Linearity priority',min_value=0.,value=1.)
            cw=c.number_input('Cost priority',min_value=0.,value=1.)
            method=st.selectbox('Search algorithm',['Genetic algorithm','Exact enumeration'])
            seed=a.number_input('Random seed',min_value=0,max_value=2147483647,value=42,step=1)
            population=b.number_input('Population',min_value=4,max_value=256,value=48,step=4)
            generations=c.number_input('Generations',min_value=1,max_value=300,value=50,step=1)
            restarts=a.number_input('GA restarts',min_value=1,max_value=10,value=3,step=1)
            verify=st.checkbox('Verify small spaces by exact enumeration',value=True)
        submitted=st.form_submit_button('Optimize designs',type='primary')
    if mode=='Exactly this many constituents':
        maximum=minimum
    elif mode=='Use all allowed fillers':
        minimum=maximum=filler_count+1
    targets=Targets(pmin,pmax,area,thickness,sensitivity,c0,nonlinearity,cost,sw,lw,cw)
    settings=dict(minimum=int(minimum),maximum=int(maximum),loadings=tuple(x/100 for x in loading_pcts),
                  method='ga' if method=='Genetic algorithm' else 'exact',seed=int(seed),population=int(population),
                  generations=int(generations),restarts=int(restarts),verify_limit=2000 if verify else 0)
    signature=json.dumps({'catalogue':fingerprint(options),'selected':selected,'targets':asdict(targets),'settings':settings},sort_keys=True)
    if submitted:
        st.session_state.pop('optimization_result',None)
        try:
            with st.spinner('Evaluating compositions, checking constraints, and searching trade-offs…'):
                result=optimize(options,selected,targets,**settings)
            st.session_state.optimization_result=result
            st.session_state.optimization_signature=signature
        except ValueError as exc:
            st.error(str(exc))
    if 'optimization_result' in st.session_state:
        if st.session_state.get('optimization_signature')!=signature:
            st.info('The settings or catalogue have changed. Run optimization again to update the results.')
        else:
            show_results(st.session_state.optimization_result)


def run():
    st.set_page_config(page_title='SensorForge · Property-driven design',page_icon='◈',layout='wide')
    st.markdown('<style>.block-container{max-width:1400px;padding-top:2rem}h1{letter-spacing:-.04em}div[data-testid="stMetric"]{background:white;padding:1rem;border-radius:12px;border:1px solid #e2e8ef}</style>',unsafe_allow_html=True)
    with st.sidebar:
        st.title('◈ SensorForge')
        st.caption('PROPERTIES → SEARCH → CANDIDATES')
        page=st.radio('Workspace',PAGES,label_visibility='collapsed')
        st.divider()
        st.caption('Evolutionary inverse design · owner-curated database · explicit physics · no model training')
    st.title(page)
    st.caption('Capacitive pressure sensors · Constrained composition and architecture optimization')
    if page=='Scientific methodology':
        st.markdown((ROOT/'docs/optimization_methodology.md').read_text())
        return
    try:
        options=read_catalog()
    except (ValueError,sqlite3.Error) as exc:
        st.error(str(exc))
        return
    if any(row['evidence_kind']=='demonstration' for row in options):
        st.warning('DEMONSTRATION DATA: the prefilled catalogue contains synthetic descriptors for testing. Results using these entries are not experimental material recommendations.')
    if page=='Option database':
        st.write('These options are maintained by the project owner. Users choose which entries the optimizer may use.')
        frame=pd.DataFrame(options)
        st.dataframe(frame,hide_index=True,width='stretch')
        st.caption(f"{len(options)} options · catalogue version {fingerprint(options)[:12]}")
        st.download_button('Download catalogue snapshot',json.dumps(options,indent=2),'catalogue_snapshot.json','application/json')
    else:
        designer(options)
