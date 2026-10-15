import streamlit as st
import pandas as pd
import networkx as nx
import streamlit.components.v1 as components
from pyvis.network import Network
import pydeck as pdk

st.set_page_config(layout="wide", page_title="Tracing the Source | Outbreak Intelligence")

# 1. LOAD DATA INTO SESSION STATE (Allows live case injection during demo)
@st.cache_data
def load_initial_data():
    return (
        pd.read_csv('synthetic_batches.csv'),
        pd.read_csv('synthetic_vendors.csv'),
        pd.read_csv('synthetic_patients.csv')
    )

if 'patients_df' not in st.session_state:
    b_df, v_df, p_df = load_initial_data()
    st.session_state.batches_df = b_df
    st.session_state.vendors_df = v_df
    st.session_state.patients_df = p_df

df_batches = st.session_state.batches_df
df_vendors = st.session_state.vendors_df
df_patients = st.session_state.patients_df

# 2. SIDEBAR: SIMULATION & LIVE HOSPITAL INTAKE
st.sidebar.title("⚙️ Outbreak Controls")
current_day = st.sidebar.slider("Timeline (Days Since Index Case)", 1, 3, 3)
prior_alpha = st.sidebar.slider("Laplace Smoothing Prior (α)", 1, 10, 1, help="Higher prior penalizes small sample sizes more aggressively.")

st.sidebar.divider()
st.sidebar.subheader("🏥 Live Hospital Case Intake")
with st.sidebar.form("new_case_form"):
    selected_vendor = st.selectbox("Reported Vendor", sorted(df_vendors['vendor_id'].unique()))
    case_status = st.radio("Patient Status", ["Sick", "Healthy"], horizontal=True)
    submitted = st.form_submit_button("➕ Inject Live Report")
    if submitted:
        new_id = f"PT-{1000 + len(df_patients) + 1}"
        new_row = pd.DataFrame([{
            'patient_id': new_id,
            'reported_vendor': selected_vendor,
            'status': case_status,
            'report_day': current_day
        }])
        st.session_state.patients_df = pd.concat([df_patients, new_row], ignore_index=True)
        st.rerun()

# 3. CORE GRAPH & BAYESIAN ENGINE (Runs globally so all views share exact scores)
available_reports = st.session_state.patients_df[st.session_state.patients_df['report_day'] <= current_day].dropna(subset=['reported_vendor'])
sick_patients = available_reports[available_reports['status'] == 'Sick']

G = nx.DiGraph()
for _, row in df_vendors.iterrows():
    G.add_edge(row['batch_received'], row['vendor_id'])
for _, row in available_reports.iterrows():
    G.add_edge(row['reported_vendor'], row['patient_id'])
    G.nodes[row['patient_id']]['status'] = row['status']

all_batches = df_batches['batch_id'].tolist()
rankings = []
batch_risk_map = {}

for batch in all_batches:
    if batch not in G:
        continue
    sick, healthy = 0, 0
    for node in nx.descendants(G, batch):
        if G.nodes[node].get('status') == 'Sick':
            sick += 1
        elif G.nodes[node].get('status') == 'Healthy':
            healthy += 1
    
    total = sick + healthy
    # Bayesian Posterior with configurable Laplace Smoothing Prior
    risk = (sick + prior_alpha) / (total + (2 * prior_alpha)) if total > 0 else 0.0
    batch_risk_map[batch] = risk
    rankings.append({
        'Batch ID': batch,
        'Bayesian Risk': risk,
        'Sick Cases': sick,
        'Healthy Controls': healthy,
        'Total Exposed': total
    })

df_rank = pd.DataFrame(rankings).sort_values(by='Bayesian Risk', ascending=False).reset_index(drop=True)
prime_suspect = df_rank.iloc[0]['Batch ID'] if not df_rank.empty else None

# HEADER & NAVIGATION
st.title("🔍 Tracing the Source: Epidemiological Traceback Engine")
view_mode = st.radio(
    "Navigation:",
    ["📊 Analytics & Bayesian Engine", "🗺️ Hotspot GIS Map (Kalyan-Dombivli-Thane)", "🕸️ Supply Chain Graph Traversal"],
    horizontal=True
)
st.divider()

# ==========================================
# VIEW 1: MAIN DASHBOARD
# ==========================================
if view_mode == "📊 Analytics & Bayesian Engine":
    active_vendors = sick_patients['reported_vendor'].nunique()
    active_wards = df_vendors[df_vendors['vendor_id'].isin(sick_patients['reported_vendor'])]['ward'].nunique()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Hospital Reports Processed", len(available_reports))
    c2.metric("Confirmed Sick Patients", len(sick_patients))
    c3.metric("Implicated Street Vendors", f"{active_vendors} / 75")
    c4.metric("Municipal Wards Affected", f"{active_wards} / 24")

    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("❌ Naive Baseline (Raw Case Frequency)")
        baseline_df = sick_patients.merge(df_vendors, left_on='reported_vendor', right_on='vendor_id')
        baseline_counts = baseline_df['batch_received'].value_counts().reset_index()
        baseline_counts.columns = ['Batch ID', 'Raw Sick Count']
        st.dataframe(baseline_counts, use_container_width=True, hide_index=True)
        st.warning("**Baseline Trap:** Raw counting falsely flags `LOT-WT-001 (Bottled Water)` because every vendor stocks it.")

    with col_b:
        st.subheader("✅ True Bayesian Engine (Laplace Smoothed)")
        st.dataframe(
            df_rank.style.format({'Bayesian Risk': '{:.2%}'})
            .background_gradient(subset=['Bayesian Risk'], cmap='Reds'),
            use_container_width=True,
            hide_index=True
        )
        if prime_suspect:
            st.success(f"🎯 **Prime Suspect Identified:** `{prime_suspect}` ({df_rank.iloc[0]['Bayesian Risk']:.1%} posterior risk)")

    st.divider()
    # VENDOR-LEVEL & REGIONAL BREAKDOWN
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        st.subheader("🏪 Top High-Risk Vendors for Inspection")
        v_stats = available_reports.groupby(['reported_vendor', 'status']).size().unstack(fill_value=0).reset_index()
        if 'Sick' not in v_stats: v_stats['Sick'] = 0
        if 'Healthy' not in v_stats: v_stats['Healthy'] = 0
        v_stats['Vendor Risk'] = (v_stats['Sick'] + 1) / (v_stats['Sick'] + v_stats['Healthy'] + 2)
        v_stats = v_stats.merge(df_vendors[['vendor_id', 'ward']].drop_duplicates(), left_on='reported_vendor', right_on='vendor_id')
        v_top = v_stats.sort_values(by=['Sick', 'Vendor Risk'], ascending=False)[['reported_vendor', 'ward', 'Sick', 'Healthy', 'Vendor Risk']].head(5)
        st.dataframe(v_top.style.format({'Vendor Risk': '{:.1%}'}), use_container_width=True, hide_index=True)

    with col_v2:
        st.subheader("📈 Regional Cluster Breakdown")
        ward_df = sick_patients.merge(df_vendors[['vendor_id', 'ward']].drop_duplicates(), left_on='reported_vendor', right_on='vendor_id')
        ward_df['Region'] = ward_df['ward'].apply(lambda x: x.split('(')[1].replace(')', '') if '(' in x else x)
        region_counts = ward_df['Region'].value_counts().reset_index()
        region_counts.columns = ['Zone', 'Confirmed Sick Cases']
        st.bar_chart(region_counts.set_index('Zone'))

# ==========================================
# VIEW 2: UPGRADED PYDECK MAP (Hover Tooltips + Scaled Radius)
# ==========================================
elif view_mode == "🗺️ Hotspot GIS Map (Kalyan-Dombivli-Thane)":
    st.subheader("Geospatial Outbreak Clusters (Thane, Dombivli, Kalyan)")
    st.caption("Hover over any circle to inspect the exact Vendor ID, Municipal Ward, and Confirmed Sick Case count.")

    if not sick_patients.empty:
        v_sickness = sick_patients['reported_vendor'].value_counts().reset_index()
        v_sickness.columns = ['vendor_id', 'sick_count']
        map_data = v_sickness.merge(df_vendors[['vendor_id', 'ward', 'lat', 'lon']].drop_duplicates(), on='vendor_id')
        map_data['radius'] = map_data['sick_count'] * 70 + 100

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_data,
            get_position='[lon, lat]',
            get_radius='radius',
            get_fill_color='[255, 75, 75, 180]',
            pickable=True,
            auto_highlight=True
        )
        view_state = pdk.ViewState(latitude=19.22, longitude=73.06, zoom=11, pitch=35)
        st.pydeck_chart(pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip={"text": "Vendor: {vendor_id}\nLocation: {ward}\nConfirmed Sick: {sick_count}"}
        ))
    else:
        st.info("No sick patients reported yet.")

# ==========================================
# VIEW 3: PYVIS SUPPLY CHAIN (Dynamic Risk Coloring + Subgraph Filter)
# ==========================================
elif view_mode == "🕸️ Supply Chain Graph Traversal":
    st.subheader("Multi-Tier Supply Chain Traceback")
    
    filter_mode = st.selectbox(
        "Graph Filter Mode:",
        ["Full Supply Chain Web", f"Isolate Prime Suspect Path ({prime_suspect})"]
    )

    net = Network(height='550px', width='100%', bgcolor='#1e1e1e', font_color='white', directed=True)
    net.repulsion(node_distance=200, central_gravity=0.1, spring_length=200, spring_strength=0.05, damping=0.95)

    # Determine which nodes to display
    if filter_mode.startswith("Isolate") and prime_suspect:
        allowed_nodes = {prime_suspect} | nx.descendants(G, prime_suspect)
    else:
        allowed_nodes = set(G.nodes())

    for node in G.nodes():
        if node not in allowed_nodes:
            continue
        if node in all_batches:
            risk_score = batch_risk_map.get(node, 0)
            # DYNAMIC COLORING BASED ON MATH, NOT STRING MATCHING
            node_color = '#ff4b4b' if node == prime_suspect else '#3b82f6'
            net.add_node(node, label=f"{node}\n(Risk: {risk_score:.0%})", color=node_color, size=35)
        elif str(node).startswith("Vendor"):
            net.add_node(node, label=str(node), color='#f59e0b', size=18)
        else:
            if G.nodes[node].get('status') == 'Sick':
                net.add_node(node, label="", title=f"Sick Patient: {node}", color='#ef4444', size=8)

    visual_nodes = set(net.get_nodes())
    for u, v in G.edges():
        if u in visual_nodes and v in visual_nodes:
            net.add_edge(u, v, color='#555555')

    net.save_graph('pyvis_graph.html')
    with open('pyvis_graph.html', 'r', encoding='utf-8') as HtmlFile:
        components.html(HtmlFile.read(), height=560)
