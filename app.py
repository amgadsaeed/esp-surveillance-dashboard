import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import zipfile
import io
import struct
import datetime

st.set_page_config(page_title="ESP Surveillance Dashboard", layout="wide")

# --- 1. Custom Binary Parser ---
def parse_welldata_dat(file_bytes):
    """
    Safely parses Baker Hughes .dat binary files.
    Reads length headers and jumps over data to prevent CPU loops.
    """
    try:
        records = []
        i = 0
        data_len = len(file_bytes)

        # Loop through the binary stream
        while i >= 0 and i < data_len - 8:
            # Find the start of the next data block
            i = file_bytes.find(b'\x02\xff', i)
            if i == -1:
                break
                
            # Find block length (number of 16-bit words)
            length = struct.unpack('>H', file_bytes[i+2:i+4])[0]
            block_size = length * 2
            
            # Guardrail to prevent infinite loops from bad bytes
            if block_size < 8 or i + block_size > data_len or block_size > 2000:
                i += 1
                continue
                
            try:
                # Extract Unix Timestamp
                ts_int = struct.unpack('>I', file_bytes[i+4:i+8])[0]
                # Validate timestamp is reasonable (between year 2000 and 2050)
                if 946684800 < ts_int < 2524608000:
                    ts = datetime.datetime.fromtimestamp(ts_int)
                    record = {'Date/Time': ts}
                    
                    # Extract Sensor ID and Value pairs
                    num_pairs = (block_size - 8) // 6
                    for p in range(num_pairs):
                        offset = i + 8 + p * 6
                        param_id = struct.unpack('>H', file_bytes[offset:offset+2])[0]
                        val = struct.unpack('>f', file_bytes[offset+2:offset+6])[0]
                        record[f'Param_{param_id:04x}'] = val
                        
                    records.append(record)
                
                # Safely jump over the parsed block
                i += block_size
            except Exception:
                i += 1

        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values('Date/Time').drop_duplicates(subset=['Date/Time']).reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Failed to parse binary data: {str(e)}")
        return pd.DataFrame()


# --- 2. Chart Rendering ---
def plot_productionlink_style(df, selected_cols):
    """Generates the ProductionLink style multi-axis chart."""
    fig = go.Figure()
    colors = ["#ff7f0e", "#8c564b", "#e377c2", "#d62728", "#17becf", "#1f77b4"]
    num_cols = len(selected_cols)
    
    # Calculate left margin offset
    left_domain_start = 0.08 * max(0, num_cols - 2) if num_cols > 2 else 0.05
    
    for i, col in enumerate(selected_cols):
        color = colors[i % len(colors)]
        yaxis_name = "y" if i == 0 else f"y{i+1}"
        
        fig.add_trace(go.Scatter(
            x=df['Date/Time'], y=df[col], name=col, 
            line=dict(color=color, width=1.5), yaxis=yaxis_name
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
            title=col, titlefont=dict(color=color, size=12), 
            tickfont=dict(color=color, size=11),
            showgrid=(i==0), gridcolor='LightGray'
        )
        
        if i == 0:
            layout_dict["yaxis"] = axis_config
        elif i == num_cols - 1 and num_cols > 1:
            axis_config.update(dict(overlaying="y", side="right"))
            layout_dict[f"yaxis{i+1}"] = axis_config
        else:
            position = left_domain_start - (0.08 * i)
            axis_config.update(dict(anchor="free", overlaying="y", side="left", position=max(0, position)))
            layout_dict[f"yaxis{i+1}"] = axis_config
            
    fig.update_layout(**layout_dict)
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    return fig


# --- 3. Main Dashboard ---
st.title("ESP Surveillance Dashboard")

# State management to prevent reloading on every click
if 'raw_data' not in st.session_state:
    st.session_state.raw_data = pd.DataFrame()
if 'sd_data' not in st.session_state:
    st.session_state.sd_data = pd.DataFrame()
if 'ev_data' not in st.session_state:
    st.session_state.ev_data = pd.DataFrame()

with st.sidebar:
    st.header("Data Import")
    uploaded_files = st.file_uploader(
        "Upload Folder (.zip) or Files", 
        type=["dat", "csv", "zip"], 
        accept_multiple_files=True
    )
    
    if st.button("Process Uploaded Files"):
        dat_frames, sd_frames, ev_frames = [], [], []
        
        with st.spinner("Decoding files..."):
            for f in uploaded_files:
                f.seek(0)
                if f.name.endswith(".zip"):
                    with zipfile.ZipFile(f) as z:
                        for filename in z.namelist():
                            if not filename.startswith("__MACOSX"):
                                file_bytes = z.read(filename)
                                if filename.endswith(".dat"):
                                    dat_frames.append(parse_welldata_dat(file_bytes))
                                elif "Event" in filename:
                                    ev_frames.append(pd.read_csv(io.BytesIO(file_bytes), on_bad_lines='skip'))
                                elif "SD" in filename or "Hist" in filename:
                                    sd_frames.append(pd.read_csv(io.BytesIO(file_bytes), on_bad_lines='skip'))
                else:
                    if f.name.endswith(".dat"):
                        dat_frames.append(parse_welldata_dat(f.read()))
                    elif "Event" in f.name:
                        ev_frames.append(pd.read_csv(f, on_bad_lines='skip'))
                    elif "SD" in f.name or "Hist" in f.name:
                        sd_frames.append(pd.read_csv(f, on_bad_lines='skip'))

        # Combine and store
        if dat_frames:
            df = pd.concat(dat_frames, ignore_index=True)
            st.session_state.raw_data = df.drop_duplicates(subset=["Date/Time"]).sort_values("Date/Time").reset_index(drop=True)
        if sd_frames:
            st.session_state.sd_data = pd.concat(sd_frames, ignore_index=True)
        if ev_frames:
            st.session_state.ev_data = pd.concat(ev_frames, ignore_index=True)
        st.success("Processing Complete!")

# Only show the dashboard if data has been processed
if not st.session_state.raw_data.empty:
    df_dat = st.session_state.raw_data
    
    # Map the internal hex IDs to the readable names from your screenshot
    rename_map = {
        "Param_00d1": "Temp-Motor",
        "Param_04bf": "Vib-Pump X axis",
        "Param_3d00": "Press-Pump Intake (Pi)", 
        "Param_1b00": "Press-Pump Discharge",
        "Param_3e00": "Temp-Pump Intake",
        "Param_04c0": "Pwr-Motor Amps Ph B"
    }
    df_dat = df_dat.rename(columns=rename_map)

    # Date Filter Configuration
    min_date = df_dat["Date/Time"].min().date()
    max_date = df_dat["Date/Time"].max().date()
    
    with st.sidebar:
        st.header("Time Filter")
        date_range = st.date_input("Select Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    
    # Apply filter safely
    if isinstance(date_range, tuple) and len(date_range) == 2:
        mask = (df_dat['Date/Time'].dt.date >= date_range[0]) & (df_dat['Date/Time'].dt.date <= date_range[1])
        df_filtered = df_dat.loc[mask]
    else:
        df_filtered = df_dat

    # Tabs
    tab_trends, tab_sd, tab_event = st.tabs(["Trends", "Shutdown History", "Event Log"])
    
    with tab_trends:
        # Get all numerical columns we can plot
        numeric_cols = df_filtered.select_dtypes(include=["float64", "float32", "int64"]).columns.tolist()
        
        # Default to the renamed columns if they exist
        default_selections = [c for c in rename_map.values() if c in numeric_cols]
        
        selected_metrics = st.multiselect(
            "Select Parameters to Plot", 
            options=numeric_cols,
            default=default_selections if default_selections else numeric_cols[:2]
        )
        
        if selected_metrics:
            st.plotly_chart(plot_productionlink_style(df_filtered, selected_metrics), use_container_width=True)
            
    with tab_sd:
        st.dataframe(st.session_state.sd_data, use_container_width=True)
            
    with tab_event:
        st.dataframe(st.session_state.ev_data, use_container_width=True)
else:
    st.info("Upload your ESP `.zip` or `.dat` / `.csv` files and click **Process Uploaded Files** in the sidebar.")
