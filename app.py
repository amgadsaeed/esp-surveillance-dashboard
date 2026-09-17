import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from parser import load_event_rec, load_sd_hist, parse_welldata_dat

st.set_page_config(page_title="ESP Surveillance Dashboard", layout="wide")

def plot_productionlink_style(df):
    """
    Generates a Plotly chart replicating the ProductionLink layout with multiple offset Y-axes.
    """
    fig = go.Figure()

    if df.empty or 'Date/Time' not in df.columns:
        return fig

    traces = [
        {"name": "Temp-Motor", "y": df.get('Motor Temp', []), "color": "#ff7f0e", "yaxis": "y1"},
        {"name": "Vib-Pump X axis", "y": df.get('Vibration X', []), "color": "#8c564b", "yaxis": "y2"},
        {"name": "Press-Pump Intake (Pi)", "y": df.get('Intake Pres', []), "color": "#e377c2", "yaxis": "y3"},
        {"name": "Press-Pump Discharge", "y": df.get('Dschrge Pres', []), "color": "#d62728", "yaxis": "y4"},
        {"name": "Temp-Pump Intake", "y": df.get('Intake Temp', []), "color": "#17becf", "yaxis": "y5"},
        {"name": "Pwr-Motor Amps Ph B", "y": df.get('Motor Amps Ph B', []), "color": "#1f77b4", "yaxis": "y6"},
    ]

    for trace in traces:
        if len(trace['y']) > 0:
            fig.add_trace(go.Scatter(
                x=df['Date/Time'], y=trace['y'], 
                name=trace['name'], 
                line=dict(color=trace['color']),
                yaxis=trace['yaxis']
            ))

    fig.update_layout(
        xaxis=dict(domain=[0.25, 0.95]), 
        yaxis=dict(title="Temp-Motor", titlefont=dict(color="#ff7f0e"), tickfont=dict(color="#ff7f0e")),
        yaxis2=dict(title="Vib-Pump X axis", titlefont=dict(color="#8c564b"), tickfont=dict(color="#8c564b"),
                    anchor="free", overlaying="y", side="left", position=0.20),
        yaxis3=dict(title="Press-Pump Intake (Pi)", titlefont=dict(color="#e377c2"), tickfont=dict(color="#e377c2"),
                    anchor="free", overlaying="y", side="left", position=0.15),
        yaxis4=dict(title="Press-Pump Discharge", titlefont=dict(color="#d62728"), tickfont=dict(color="#d62728"),
                    anchor="free", overlaying="y", side="left", position=0.10),
        yaxis5=dict(title="Temp-Pump Intake", titlefont=dict(color="#17becf"), tickfont=dict(color="#17becf"),
                    anchor="free", overlaying="y", side="left", position=0.05),
        yaxis6=dict(title="Pwr-Motor Amps Ph B", titlefont=dict(color="#1f77b4"), tickfont=dict(color="#1f77b4"),
                    overlaying="y", side="right"),
        margin=dict(l=20, r=20, t=40, b=20),
        height=750,
        showlegend=False,
        hovermode="x unified",
        plot_bgcolor="white"
    )
    
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')

    return fig

# --- UI Layout ---
st.title("ESP Surveillance Dashboard")

with st.sidebar:
    st.header("Data Import")
    uploaded_dat = st.file_uploader("Upload WellData File (.dat)", type=['dat', 'txt', 'exe'])
    uploaded_event = st.file_uploader("Upload Event Rec File (.csv)", type=['csv'])
    uploaded_sd = st.file_uploader("Upload SD Hist File (.csv)", type=['csv'])
    
    st.header("Time Filter")
    date_range = st.date_input("Select Date Range", value=None)

df_raw = pd.DataFrame()
df_event = pd.DataFrame()
df_sd = pd.DataFrame()

if uploaded_dat:
    df_raw = parse_welldata_dat(uploaded_dat)
if uploaded_event:
    df_event = load_event_rec(uploaded_event)
if uploaded_sd:
    df_sd = load_sd_hist(uploaded_sd)

if not df_raw.empty and len(date_range) == 2:
    start_date, end_date = date_range
    mask = (df_raw['Date/Time'].dt.date >= start_date) & (df_raw['Date/Time'].dt.date <= end_date)
    df_raw = df_raw.loc[mask]

tab_trends, tab_sd, tab_event = st.tabs(["Trends", "Shutdown History", "Event Log"])

with tab_trends:
    if not df_raw.empty:
        st.plotly_chart(plot_productionlink_style(df_raw), use_container_width=True)
    else:
        st.info("Upload '26-08-15 WellData.dat' to generate the trend dashboard.")

with tab_sd:
    if not df_sd.empty:
        st.dataframe(df_sd, use_container_width=True)
    else:
        st.info("Upload '26-08-15 SD Hist.csv' to view shutdown history.")

with tab_event:
    if not df_event.empty:
        st.dataframe(df_event, use_container_width=True)
    else:
        st.info("Upload '26-08-15 Event Rec.csv' to view the event log.")
