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
        st.error(f"Failed to parse binary data: {str(e)}")
        return pd.DataFrame()


# --- 2. Chart Rendering ---
def plot_productionlink_style(df, selected_cols, axis_configs):
    fig = go.Figure()
    num_cols = len(selected_cols)
    
    max_left_margin = 0.70
    if num_cols > 2:
        offset_spacing = min(0.08, max_left_margin / (num_cols - 2))
        left_domain_start = offset_spacing * (num_cols - 2)
    else:
        offset_spacing = 0.08
        left_domain_start = 0.05
    
    for i, col in enumerate(selected_cols):
        color = axis_configs[col]['color']
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
        "height": 750,
        "showlegend": True,
        "legend": dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    }
    
    for i, col in enumerate(selected_cols):
        conf = axis_configs[col]
        color = conf['color']
        
        axis_config = dict(
            title=dict(text=col, font=dict(color=color, size=12)), 
            tickfont=dict(color=color, size=11),
            showgrid=(i==0), gridcolor='LightGray'
        )
        
        # Apply custom scale if Auto-scale is disabled
        if not conf['auto']:
            axis_config['range'] = [conf['min'], conf['max']]
            axis_config['autorange'] = False
        
        if i == 0:
            layout_dict["yaxis"] = axis_config
        elif i == num_cols - 1 and num_cols > 1:
            axis_config.update(dict(overlaying="y", side="right"))
            layout_dict[f"yaxis{i+1}"] = axis_config
        else:
            position = left_domain_start - (offset_spacing * i)
            bound_position = max(0.0, min(1.0, position))
            axis_config.update(dict(anchor="free", overlaying="y", side="left", position=bound_position))
            layout_dict[f"yaxis{i+1}"] = axis_config
            
    fig.update_layout(**layout_dict)
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    return fig


# --- 3. Main Dashboard ---
st.title("ESP Surveillance Dashboard")

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
        with st.spinner("Decoding files... This may take a moment."):
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

        if dat_frames:
            df = pd.concat(dat_frames, ignore_index=True)
            st.session_state.raw_data = df.drop_duplicates(subset=["Date/Time"]).sort_values("Date/Time").reset_index(drop=True)
        if sd_frames:
            st.session_state.sd_data = pd.concat(sd_frames, ignore_index=True)
        if ev_frames:
            st.session_state.ev_data = pd.concat(ev_frames, ignore_index=True)
        st.success("Processing Complete!")

if not st.session_state.raw_data.empty:
    df_dat = st.session_state.raw_data
    
    # Expanded Dictionary mapping internal hex IDs to readable names
    # You can add or modify these exact names anytime
    rename_map = {
        "Param_00d1": "Temp-Motor",
        "Param_04bf": "Vib-Pump X axis",
        "Param_04c0": "Vib-Pump Y axis",
        "Param_3d00": "Press-Pump Intake (Pi)", 
        "Param_1b00": "Press-Pump Discharge",
        "Param_3e00": "Temp-Pump Intake",
        "Param_06aa": "Converter Phase B Amps",
        "Param_06ab": "Converter Phase C Amps",
        "Param_0701": "Set Frequency",
        "Param_0005": "Output Frequency",
        "Param_0009": "Output Volts",
        "Param_000a": "Bus Volts"
    }
    df_dat = df_dat.rename(columns=rename_map)

    min_date = df_dat["Date/Time"].min().date()
    max_date = df_dat["Date/Time"].max().date()
    
    with st.sidebar:
        st.header("Time Filter")
        date_range = st.date_input("Select Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    
    if isinstance(date_range, tuple) and len(date_range) == 2:
        mask = (df_dat['Date/Time'].dt.date >= date_range[0]) & (df_dat['Date/Time'].dt.date <= date_range[1])
        df_filtered = df_dat.loc[mask]
    else:
        df_filtered = df_dat

    tab_trends, tab_sd, tab_event = st.tabs(["Trends", "Shutdown History", "Event Log"])
    
    with tab_trends:
        numeric_cols = df_filtered.select_dtypes(include=["float64", "float32", "int64"]).columns.tolist()
        default_selections = [c for c in rename_map.values() if c in numeric_cols]
        
        selected_metrics = st.multiselect(
            "Select Parameters to Plot", 
            options=numeric_cols,
            default=default_selections[:4] if default_selections else numeric_cols[:2],
            max_selections=10
        )
        
        # --- NEW: Dynamic Color and Scale Configurations ---
        axis_configs = {}
        default_colors = ["#ff7f0e", "#8c564b", "#e377c2", "#d62728", "#17becf", "#1f77b4", "#2ca02c", "#9467bd"]
        
        if selected_metrics:
            with st.expander("🎨 Customize Parameter Colors & Scales (Prevent Overlap)", expanded=False):
                st.markdown("Uncheck 'Auto Scale' to manually set the Min and Max axis bounds. Pushing a trace's Max value much higher than its actual data will move it to the bottom of the chart.")
                
                for i, metric in enumerate(selected_metrics):
                    cols = st.columns([3, 1, 2, 2, 2])
                    
                    with cols[0]:
                        st.markdown(f"**{metric}**")
                    with cols[1]:
                        color = st.color_picker(f"Color {i}", value=default_colors[i % len(default_colors)], key=f"color_{metric}", label_visibility="collapsed")
                    with cols[2]:
                        auto_scale = st.checkbox("Auto Scale", value=True, key=f"auto_{metric}")
                    with cols[3]:
                        y_min = st.number_input("Min Axis Value", value=0.0, key=f"min_{metric}", disabled=auto_scale, label_visibility="collapsed")
                    with cols[4]:
                        y_max = st.number_input("Max Axis Value", value=1000.0, key=f"max_{metric}", disabled=auto_scale, label_visibility="collapsed")
                        
                    axis_configs[metric] = {"color": color, "auto": auto_scale, "min": y_min, "max": y_max}

            # Downsample if extremely large to prevent crashing
            max_points = 10000
            if len(df_filtered) > max_points:
                step = len(df_filtered) // max_points
                plot_df = df_filtered.iloc[::step]
                st.caption(f"⚠️ *Displaying {max_points:,} downsampled points out of {len(df_filtered):,} available records for browser performance.*")
            else:
                plot_df = df_filtered

            st.plotly_chart(plot_productionlink_style(plot_df, selected_metrics, axis_configs), use_container_width=True)
            
    with tab_sd:
        st.dataframe(st.session_state.sd_data, use_container_width=True)
            
    with tab_event:
        st.dataframe(st.session_state.ev_data, use_container_width=True)
else:
    st.info("Upload your ESP `.zip` or `.dat` / `.csv` files and click **Process Uploaded Files** in the sidebar.")
