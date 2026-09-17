import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from parser import parse_welldata_dat, parse_csv
import zipfile
import io

st.set_page_config(page_title="ESP Surveillance Dashboard", layout="wide")

# --- Dynamic Charting Logic ---
def plot_dynamic_multiaxis(df, selected_cols):
    """
    Builds a ProductionLink style chart. 
    Dynamically stacks Y-axes on the left, puts the last selected axis on the right.
    """
    fig = go.Figure()
    
    # Theme colors inspired by standard ESP software
    colors = ["#ff7f0e", "#8c564b", "#e377c2", "#d62728", "#17becf", "#1f77b4"]
    num_cols = len(selected_cols)
    
    # Calculate how much margin space to leave on the left based on number of axes selected
    left_domain_start = 0.08 * max(0, num_cols - 2) if num_cols > 2 else 0.05
    
    for i, col in enumerate(selected_cols):
        color = colors[i % len(colors)]
        yaxis_name = "y" if i == 0 else f"y{i+1}"
        
        fig.add_trace(go.Scatter(
            x=df['Date/Time'], 
            y=df[col], 
            name=col, 
            line=dict(color=color, width=1.5),
            yaxis=yaxis_name
        ))
    
    layout_dict = {
        "xaxis": dict(domain=[left_domain_start, 0.95]),
        "margin": dict(l=20, r=20, t=40, b=20),
        "hovermode": "x unified",
        "plot_bgcolor": "white",
        "height": 700,
        "showlegend": True,
        "legend": dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    }
    
    for i, col in enumerate(selected_cols):
        color = colors[i % len(colors)]
        axis_config = dict(
            title=col, 
            titlefont=dict(color=color, size=12), 
            tickfont=dict(color=color, size=11),
            showgrid=(i==0), # Only show grid for the first axis to prevent clutter
            gridcolor='LightGray'
        )
        
        if i == 0:
            layout_dict["yaxis"] = axis_config
        elif i == num_cols - 1 and num_cols > 1:
            # Put the very last parameter on the right side
            axis_config.update(dict(overlaying="y", side="right"))
            layout_dict[f"yaxis{i+1}"] = axis_config
        else:
            # Intermediate axes stack vertically separated on the left
            position = left_domain_start - (0.08 * i)
            axis_config.update(dict(anchor="free", overlaying="y", side="left", position=max(0, position)))
            layout_dict[f"yaxis{i+1}"] = axis_config
            
    fig.update_layout(**layout_dict)
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    return fig

# --- Data Loading Logic ---
@st.cache_data
def load_all_data(uploaded_files):
    dat_frames, sd_frames, ev_frames = [], [], []

    def process_file(filename, file_bytes):
        if filename.endswith(".dat"):
            df = parse_welldata_dat(io.BytesIO(file_bytes))
            if not df.empty:
                dat_frames.append(df)
        elif "SD Hist" in filename or "SD" in filename:
            df = parse_csv(io.BytesIO(file_bytes))
            if not df.empty:
                sd_frames.append(df)
        elif "Event" in filename:
            df = parse_csv(io.BytesIO(file_bytes))
            if not df.empty:
                ev_frames.append(df)

    # Process zip files or individual files
    for f in uploaded_files:
        if f.name.endswith(".zip"):
            with zipfile.ZipFile(f) as z:
                for filename in z.namelist():
                    if not filename.startswith("__MACOSX"):
                        with z.open(filename) as extracted_file:
                            process_file(filename, extracted_file.read())
        else:
            process_file(f.name, f.read())

    # Compile frames
    df_dat = pd.concat(dat_frames, ignore_index=True) if dat_frames else pd.DataFrame()
    if not df_dat.empty and 'Date/Time' in df_dat.columns:
        df_dat = df_dat.drop_duplicates(subset=["Date/Time"]).sort_values("Date/Time").reset_index(drop=True)
        
    df_sd = pd.concat(sd_frames, ignore_index=True) if sd_frames else pd.DataFrame()
    df_ev = pd.concat(ev_frames, ignore_index=True) if ev_frames else pd.DataFrame()

    return df_dat, df_sd, df_ev

# --- Main App UI ---
st.title("ESP Surveillance Dashboard")

with st.sidebar:
    st.header("Data Import")
    uploaded_files = st.file_uploader(
        "Upload Folder (.zip) or Multiple Files", 
        type=["dat", "csv", "zip", "txt"], 
        accept_multiple_files=True,
        help="Drag and drop your .dat and .csv files here, or upload a ZIP file containing them."
    )

if uploaded_files:
    df_dat, df_sd, df_ev = load_all_data(uploaded_files)
    
    if not df_dat.empty:
        # Date Filter Configuration
        min_date = df_dat["Date/Time"].min().date()
        max_date = df_dat["Date/Time"].max().date()
        
        with st.sidebar:
            st.header("Time Filter")
            date_range = st.date_input("Select Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        
        # Apply time filter
        if isinstance(date_range, tuple) and len(date_range) == 2:
            mask = (df_dat['Date/Time'].dt.date >= date_range[0]) & (df_dat['Date/Time'].dt.date <= date_range[1])
            df_filtered = df_dat.loc[mask]
        else:
            df_filtered = df_dat
            
        # Render tabs
        tab_trends, tab_sd, tab_event = st.tabs(["Trends", "Shutdown History", "Event Log"])
        
        with tab_trends:
            # Map known internal parameters to readable names 
            # (You can adjust these hex codes based on your specific ESP configurations)
            rename_map = {
                "Param_00d1": "Motor Temp",
                "Param_04c0": "Amps Phase B",
                "Param_000a": "Bus Volts",
                "Param_06aa": "Converter Phase B Amps",
                "Param_04bf": "Vibration X",
            }
            df_filtered = df_filtered.rename(columns=rename_map)
            
            # Fetch all plottable numeric columns
            numeric_cols = df_filtered.select_dtypes(include=["float64", "float32", "int64"]).columns.tolist()
            
            selected_metrics = st.multiselect(
                "Select Parameters to Plot", 
                options=numeric_cols,
                default=[c for c in numeric_cols if c in rename_map.values()][:5] if any(c in rename_map.values() for c in numeric_cols) else numeric_cols[:2]
            )
            
            if selected_metrics:
                st.plotly_chart(plot_dynamic_multiaxis(df_filtered, selected_metrics), use_container_width=True)
            else:
                st.warning("Please select at least one parameter to view the trend chart.")
                
        with tab_sd:
            if not df_sd.empty:
                st.dataframe(df_sd, use_container_width=True)
            else:
                st.info("No Shutdown History data found in the uploaded files.")
                
        with tab_event:
            if not df_ev.empty:
                st.dataframe(df_ev, use_container_width=True)
            else:
                st.info("No Event Rec data found in the uploaded files.")
    else:
        st.warning("No trend data extracted. Check your file format.")
else:
    st.info("Please upload your ESP files or a `.zip` archive containing them using the sidebar.")
