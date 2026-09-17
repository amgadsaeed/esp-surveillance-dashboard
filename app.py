import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import zipfile
import io
import struct
import datetime

# --- Page Configuration ---
st.set_page_config(page_title="ESP Surveillance", layout="wide")

# --- 1. Custom Binary Parser ---
@st.cache_data
def parse_welldata_dat(file_bytes):
    try:
        records = []
        i = 0
        data_len = len(file_bytes)

        while i >= 0 and i < data_len - 8:
            i = file_bytes.find(b'\x02\xff', i)
            if i == -1: break
                
            length = struct.unpack('>H', file_bytes[i+2:i+4])[0]
            block_size = length * 2
            
            if block_size < 8 or i + block_size > data_len or block_size > 2000:
                i += 1
                continue
                
            try:
                ts_int = struct.unpack('>I', file_bytes[i+4:i+8])[0]
                if 946684800 < ts_int < 2524608000:
                    ts = datetime.datetime.fromtimestamp(ts_int)
                    record = {'Date/Time': ts}
                    
                    num_pairs = (block_size - 8) // 6
                    for p in range(num_pairs):
                        offset = i + 8 + p * 6
                        param_id = struct.unpack('>H', file_bytes[offset:offset+2])[0]
                        val = struct.unpack('>f', file_bytes[offset+2:offset+6])[0]
                        record[f'Param_{param_id:04x}'] = val
                        
                    records.append(record)
                i += block_size
            except Exception:
                i += 1

        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values('Date/Time').drop_duplicates(subset=['Date/Time']).reset_index(drop=True)
        return df
    except Exception as e:
        return pd.DataFrame()

# --- 2. Advanced Chart Rendering ---
def plot_productionlink_style(df, selected_cols, axis_configs):
    fig = go.Figure()
    
    left_axes = [col for col in selected_cols if axis_configs[col]['side'] == 'Left']
    right_axes = [col for col in selected_cols if axis_configs[col]['side'] == 'Right']
    
    # Smart margins to prevent crowded axes
    AXIS_SPACING = 0.055 
    domain_start = min(0.4, len(left_axes) * AXIS_SPACING) if left_axes else 0.02
    domain_end = max(0.6, 1.0 - (len(right_axes) * AXIS_SPACING)) if right_axes else 0.98

    # Map units for clean tooltips (Matches screenshot)
    unit_map = {
        "Temp-Motor": "degF", "DH Sensor Motor Temperature": "degF",
        "Temp-Pump Intake": "degF", "Vib-Pump X axis": "G", "Vib-Pump Y axis": "G",
        "Press-Pump Intake (Pi)": "psi", "Press-Pump Discharge": "psi",
        "Pwr-Motor Amps Ph B": "A", "Converter Phase C Amps": "A", 
        "Output Current A": "A", "Output Current C": "A",
        "Output Frequency": "Hz", "Set Frequency": "Hz", "Status-Hz": "Hz",
        "Output Volts": "V", "Bus Volts": "V", "Present Motor RPM": "RPM"
    }

    # Add Traces
    for i, col in enumerate(selected_cols):
        conf = axis_configs[col]
        yaxis_name = "y" if i == 0 else f"y{i+1}"
        unit = unit_map.get(col, "")
        
        fig.add_trace(go.Scatter(
            x=df['Date/Time'], 
            y=df[col], 
            name=col, 
            line=dict(color=conf['color'], width=1.5, dash=conf['dash']), 
            yaxis=yaxis_name,
            mode='lines',
            # This forces the clean tooltip: Just "Value Unit" (e.g., "240.0 degF")
            hovertemplate=f"%{{y:,.1f}} {unit}<extra></extra>" 
        ))
    
    # Unified Layout configuration
    layout_dict = {
        "xaxis": dict(
            domain=[domain_start, domain_end],
            showgrid=True, gridcolor='#E5E5E5',
            # Formats the top of the tooltip to match screenshot: "09/17/2026 \n 01:08"
            hoverformat="%m/%d/%Y<br>%H:%M",
            # The Yellow Spikeline
            showspikes=True, spikemode="across", spikethickness=1.5, spikecolor="gold", spikedash="solid"
        ),
        "margin": dict(l=10, r=10, t=30, b=20),
        "hovermode": "x unified",
        "hoverlabel": dict(bgcolor="white", font_size=13, bordercolor="#D3D3D3"),
        "plot_bgcolor": "white",
        "paper_bgcolor": "white",
        "height": 550,  # Reduced from 750px to eliminate scrolling
        "showlegend": False 
    }
    
    # Position the Y Axes
    for i, col in enumerate(selected_cols):
        conf = axis_configs[col]
        is_right = conf['side'] == 'Right'
        
        axis_config = dict(
            title=dict(text=col, font=dict(color=conf['color'], size=13)), 
            tickfont=dict(color=conf['color'], size=12),
            showgrid=(i==0), gridcolor='#E5E5E5',
            zeroline=False, anchor="free",
            overlaying="y" if i > 0 else None,
            side="right" if is_right else "left"
        )
        
        # Space the axes out horizontally
        if is_right:
            idx = right_axes.index(col)
            axis_config['position'] = min(1.0, domain_end + (idx * AXIS_SPACING))
        else:
            idx = left_axes.index(col)
            axis_config['position'] = max(0.0, domain_start - (idx * AXIS_SPACING))
            
        # Apply manual scales
        if not conf['auto']:
            axis_config['range'] = [conf['min'], conf['max']]
            axis_config['autorange'] = False
            
        layout_dict["yaxis" if i == 0 else f"yaxis{i+1}"] = axis_config
            
    fig.update_layout(**layout_dict)
    return fig


# --- 3. UI Application ---
st.title("ESP Surveillance Dashboard")

# Memory State
if 'raw_data' not in st.session_state: st.session_state.raw_data = pd.DataFrame()
if 'sd_data' not in st.session_state: st.session_state.sd_data = pd.DataFrame()
if 'ev_data' not in st.session_state: st.session_state.ev_data = pd.DataFrame()

# Sidebar: File Upload
with st.sidebar:
    st.header("Data Import")
    uploaded_files = st.file_uploader("Upload .zip or multiple files", type=["dat", "csv", "zip"], accept_multiple_files=True)
    
    if st.button("Process Files", type="primary"):
        dat_frames, sd_frames, ev_frames = [], [], []
        
        with st.spinner("Decoding files..."):
            for f in uploaded_files:
                f.seek(0)
                if f.name.endswith(".zip"):
                    with zipfile.ZipFile(f) as z:
                        for filename in z.namelist():
                            if not filename.startswith("__MACOSX"):
                                file_bytes = z.read(filename)
                                if filename.endswith(".dat"): dat_frames.append(parse_welldata_dat(file_bytes))
                                elif "Event" in filename: ev_frames.append(pd.read_csv(io.BytesIO(file_bytes), on_bad_lines='skip'))
                                elif "SD" in filename or "Hist" in filename: sd_frames.append(pd.read_csv(io.BytesIO(file_bytes), on_bad_lines='skip'))
                else:
                    if f.name.endswith(".dat"): dat_frames.append(parse_welldata_dat(f.read()))
                    elif "Event" in f.name: ev_frames.append(pd.read_csv(f, on_bad_lines='skip'))
                    elif "SD" in f.name or "Hist" in f.name: sd_frames.append(pd.read_csv(f, on_bad_lines='skip'))

        if dat_frames:
            df = pd.concat(dat_frames, ignore_index=True)
            st.session_state.raw_data = df.drop_duplicates(subset=["Date/Time"]).sort_values("Date/Time").reset_index(drop=True)
        if sd_frames: st.session_state.sd_data = pd.concat(sd_frames, ignore_index=True)
        if ev_frames: st.session_state.ev_data = pd.concat(ev_frames, ignore_index=True)
        st.success("Complete!")

# Main Dashboard View
if not st.session_state.raw_data.empty:
    df_dat = st.session_state.raw_data
    
    # Map raw hex tags to familiar ProductionLink names
    rename_map = {
        "Param_061d": "Temp-Motor", "Param_033f": "DH Sensor Motor Temperature",
        "Param_061a": "Press-Pump Intake (Pi)", "Param_061b": "Press-Pump Discharge",
        "Param_061c": "Temp-Pump Intake", "Param_06aa": "Pwr-Motor Amps Ph B",
        "Param_06ab": "Converter Phase C Amps", "Param_0006": "Output Current A",
        "Param_0008": "Output Current C", "Param_0005": "Output Frequency",
        "Param_0009": "Output Volts", "Param_000a": "Bus Volts",
        "Param_050c": "Present Motor RPM", "Param_0701": "Status-Hz",
        "Param_04bf": "Vib-Pump X axis", "Param_04c0": "Vib-Pump Y axis",
        "Param_00d1": "Power Factor",
    }
    df_dat = df_dat.rename(columns=rename_map)

    # Date Filter
    min_date, max_date = df_dat["Date/Time"].min().date(), df_dat["Date/Time"].max().date()
    with st.sidebar:
        st.header("Time Filter")
        date_range = st.date_input("Select Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    
    if isinstance(date_range, tuple) and len(date_range) == 2:
        df_filtered = df_dat.loc[(df_dat['Date/Time'].dt.date >= date_range[0]) & (df_dat['Date/Time'].dt.date <= date_range[1])]
    else:
        df_filtered = df_dat

    # Tabs
    tab_trends, tab_sd, tab_event = st.tabs(["Trends", "Shutdown History", "Event Log"])
    
    with tab_trends:
        numeric_cols = df_filtered.select_dtypes(include=["float64", "float32", "int64"]).columns.tolist()
        default_selections = [c for c in rename_map.values() if c in numeric_cols][:6]
        
        # Simplified Parameter Dropdown
        selected_metrics = st.multiselect("Select Parameters to Plot", options=numeric_cols, default=default_selections, max_selections=12)
        
        axis_configs = {}
        default_colors = {"Temp-Motor": "#ff7f0e", "Vib-Pump X axis": "#8c564b", "Press-Pump Intake (Pi)": "#e377c2", 
                          "Press-Pump Discharge": "#d62728", "Temp-Pump Intake": "#17becf", "Pwr-Motor Amps Ph B": "#0000ff", "Status-Hz": "#000000"}
        fallback_colors = ["#2ca02c", "#9467bd", "#bcbd22", "#7f7f7f"]
        
        if selected_metrics:
            with st.expander("⚙️ Advanced Axis & Style Configuration", expanded=False):
                st.markdown("Adjust colors, sides, and scales. Uncheck 'Auto' to set manual Min/Max values and avoid line overlapping.")
                for i, metric in enumerate(selected_metrics):
                    def_col = default_colors.get(metric, fallback_colors[i % len(fallback_colors)])
                    def_side = "Right" if any(x in metric for x in ["Amps", "Hz", "Frequency", "Volts"]) else "Left"
                    def_dash = "dash" if "Vib" in metric or "Status" in metric else "solid"

                    cols = st.columns([2.5, 1, 1, 1.5, 1, 1.5, 1.5])
                    with cols[0]: st.markdown(f"**{metric}**")
                    with cols[1]: color = st.color_picker("Color", value=def_col, key=f"col_{metric}", label_visibility="collapsed")
                    with cols[2]: side = st.selectbox("Side", ["Left", "Right"], index=0 if def_side=="Left" else 1, key=f"side_{metric}", label_visibility="collapsed")
                    with cols[3]: dash = st.selectbox("Style", ["solid", "dash", "dot"], index=["solid", "dash", "dot"].index(def_dash), key=f"dash_{metric}", label_visibility="collapsed")
                    with cols[4]: auto_scale = st.checkbox("Auto", value=True, key=f"auto_{metric}")
                    with cols[5]: y_min = st.number_input("Min", value=0.0, key=f"min_{metric}", disabled=auto_scale, label_visibility="collapsed")
                    with cols[6]: y_max = st.number_input("Max", value=5000.0, key=f"max_{metric}", disabled=auto_scale, label_visibility="collapsed")
                        
                    axis_configs[metric] = {"color": color, "side": side, "dash": dash, "auto": auto_scale, "min": y_min, "max": y_max}

            # Downsample to avoid browser lag
            max_points = 10000
            if len(df_filtered) > max_points:
                step = len(df_filtered) // max_points
                plot_df = df_filtered.iloc[::step]
            else:
                plot_df = df_filtered

            st.plotly_chart(plot_productionlink_style(plot_df, selected_metrics, axis_configs), use_container_width=True)
            
    with tab_sd: st.dataframe(st.session_state.sd_data, use_container_width=True)
    with tab_event: st.dataframe(st.session_state.ev_data, use_container_width=True)
else:
    st.info("Upload your ESP `.zip` or data files and click **Process Files** in the sidebar.")
