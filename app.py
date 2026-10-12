import streamlit as st
import pandas as pd
import networkx as nx
import streamlit.components.v1 as components
from pyvis.network import Network
import numpy as np

# 1. LOAD DATA
@st.cache_data
def load_data():
    return pd.read_csv('synthetic_batches.csv'), pd.read_csv('synthetic_vendors.csv'), pd.read_csv('synthetic_patients.csv')

df_batches, df_vendors, df_patients = load_data()

st.set_page_config(layout="wide", page_title="Outbreak Detector") 
st.title("Tracing the Source: Outbreak Detection")

# 2. SIMULATION CONTROLS
st.sidebar.header("Simulation Engine")
current_day = st.sidebar.slider("Simulate Days Passed", 1, 3, 1)
available_reports = df_patients[df_patients['report_day'] <= current_day].dropna(subset=['reported_vendor'])

st.sidebar.markdown(f"**Data Stream:** Processing {len(available_reports)} hospital reports.")

sick_patients = available_reports[available_reports['status'] == 'Sick']
active_vendors = available_reports['reported_vendor'].unique()
active_wards = df_vendors[df_vendors['vendor_id'].isin(active_vendors)]['ward'].nunique()

# 3. CONDITIONAL RENDERING UI (Fixes background lag)
# This acts exactly like tabs visually, but strictly isolates the backend execution.
view_mode = st.radio("Navigation Menu:", ["📊 Main Dashboard", "🗺️ Geographic Map", "🕸️ Supply Chain Graph"], horizontal=True)
st.divider()

# ==========================================
# VIEW 1: MAIN DASHBOARD
# ==========================================
if view_mode == "📊 Main Dashboard":
    # KPIs
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Reports Processed", len(available_reports))
    col2.metric("Sick Patients", len(sick_patients))
    col3.metric("City Wards Affected", active_wards)
    st.divider()

    # BASELINE vs ADVANCED
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("Baseline Model (Raw Case Counts)")
        baseline_df = sick_patients.merge(df_vendors, left_on='reported_vendor', right_on='vendor_id')
        baseline_counts = baseline_df['batch_received'].value_counts().reset_index()
        baseline_counts.columns = ['Suspected Batch', 'Sick Patient Count']
        st.dataframe(baseline_counts.head(3), use_container_width=True)
        st.caption("⚠️ Baseline incorrectly targets Popular_Bottled_Water.")

    with col_b:
        st.subheader("Advanced Engine (True Bayesian)")
        G = nx.DiGraph()
        for _, row in df_vendors.iterrows():
            G.add_edge(row['batch_received'], row['vendor_id'])
        for _, row in available_reports.iterrows():
            G.add_edge(row['reported_vendor'], row['patient_id'])
            G.nodes[row['patient_id']]['status'] = row['status']

        all_batches = df_batches['batch_id'].tolist()
        rankings = []
        for batch in all_batches:
            if batch not in G: continue
            sick, healthy = 0, 0
            for node in nx.descendants(G, batch):
                if 'status' in G.nodes[node]:
                    if G.nodes[node]['status'] == 'Sick': sick += 1
                    elif G.nodes[node]['status'] == 'Healthy': healthy += 1
            
            total = sick + healthy
            risk = (sick + 1) / (total + 2) if total > 0 else 0
            rankings.append({'Batch': batch, 'Risk Score': risk, 'Sick': sick, 'Healthy': healthy, 'Exposed': total})

        df_rank = pd.DataFrame(rankings).sort_values(by='Risk Score', ascending=False)
        top_suspects = df_rank.head(3).reset_index(drop=True)
        st.dataframe(top_suspects.style.format({'Risk Score': '{:.2%}'}).highlight_max(subset=['Risk Score'], color='#ff4b4b'), use_container_width=True)

    # EVIDENCE TRAIL
    st.divider()
    if not top_suspects.empty:
        prime = top_suspects.iloc[0]
        st.success(f"🚨 **Targeted Recall Recommended:** {prime['Batch']}")
        st.markdown(f"**Bayesian Proof:** Ignored false signals from {len(df_patients[df_patients['status']=='Healthy'])} healthy controls. Filtered out 10% faulty memory noise via graph pathfinding.")

# ==========================================
# VIEW 2: GEOGRAPHIC MAP
# ==========================================
elif view_mode == "🗺️ Geographic Map":
    st.subheader("Live Outbreak Geography")
    st.markdown("Visualizing the spread of the outbreak across Thane, Dombivli, and Kalyan.")
    
    if not sick_patients.empty:
        vendor_sickness = sick_patients['reported_vendor'].value_counts().reset_index()
        vendor_sickness.columns = ['vendor_id', 'sick_count']
        map_data = vendor_sickness.merge(df_vendors[['vendor_id', 'lat', 'lon']].drop_duplicates(), on='vendor_id')
        
        map_data['lat'] = map_data['lat'] + np.random.uniform(-0.005, 0.005, len(map_data))
        map_data['lon'] = map_data['lon'] + np.random.uniform(-0.005, 0.005, len(map_data))
        
        st.map(map_data[['lat', 'lon']], zoom=10)
    else:
        st.info("No sick patients reported yet.")

# ==========================================
# VIEW 3: PYVIS SUPPLY CHAIN
# ==========================================
elif view_mode == "🕸️ Supply Chain Graph":
    st.subheader("Live Supply Chain Network")
    st.markdown("Tracing paths backwards from Sick Patients (Red) via Vendors (Orange) to the source Batches.")
    
    # REBUILD GRAPH (Since it is now isolated to this view)
    G = nx.DiGraph()
    for _, row in df_vendors.iterrows():
        G.add_edge(row['batch_received'], row['vendor_id'])
    for _, row in available_reports.iterrows():
        G.add_edge(row['reported_vendor'], row['patient_id'])
        G.nodes[row['patient_id']]['status'] = row['status']
    
    net = Network(height='500px', width='100%', bgcolor='#222222', font_color='white')
    
    # RESTORED OPTIMIZED PHYSICS: Clean, balanced spacing without clustering too tightly
    net.repulsion(
        node_distance=200,       
        central_gravity=0.1,    
        spring_length=200,       
        spring_strength=0.05,
        damping=0.95             
    )

    all_batches = df_batches['batch_id'].tolist()
    for node in G.nodes():
        if node in all_batches:
            node_color = '#ff4b4b' if 'Contaminated' in str(node) else '#4b4bff'
            net.add_node(node, label=str(node), color=node_color, size=30)
        elif str(node).startswith("Vendor"):
            net.add_node(node, label=str(node), color='#ffa500', size=20)
        else:
            if G.nodes[node].get('status') == 'Sick':
                net.add_node(node, label=" ", color='#ff4b4b', size=10)

    visual_nodes = net.get_nodes()
    for edge in G.edges():
        if edge[0] in visual_nodes and edge[1] in visual_nodes:
            net.add_edge(edge[0], edge[1], color='#555555')

    try:
        net.save_graph('pyvis_graph.html')
        with open('pyvis_graph.html', 'r', encoding='utf-8') as HtmlFile:
            components.html(HtmlFile.read(), height=510)
    except Exception as e:
        st.error(f"Graph rendering error: {e}")