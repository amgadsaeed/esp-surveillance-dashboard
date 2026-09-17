import pandas as pd
import struct
import datetime

def parse_welldata_dat(file_obj):
    """
    Parses the proprietary Baker Hughes .dat binary file.
    Extracts the Unix timestamps and floating-point parameter values.
    """
    try:
        # Read the raw byte data
        data = file_obj.read()
        
        # Fallback if a text/csv file was accidentally passed
        if isinstance(data, str):
            file_obj.seek(0)
            return pd.read_csv(file_obj)

        # Centrigraph dat files separate telemetry blocks with 0x02 0xff
        blocks = data.split(b'\x02\xff')
        records = []
        
        for b in blocks:
            if len(b) < 6: 
                continue
            
            # Re-attach the separator we split on
            b = b'\x02\xff' + b
            
            try:
                # Length is the number of 16-bit words (total bytes = length * 2)
                length = struct.unpack('>H', b[2:4])[0]
                if len(b) < length * 2:
                    continue
                
                # Extract the Unix timestamp
                ts_int = struct.unpack('>I', b[4:8])[0]
                ts = datetime.datetime.fromtimestamp(ts_int)
                record = {'Date/Time': ts}
                
                # Extract parameter pairs (ID: 2 bytes, Value: 4 bytes float)
                num_pairs = (len(b) - 8) // 6
                for i in range(num_pairs):
                    param_id = struct.unpack('>H', b[8+i*6 : 10+i*6])[0]
                    val = struct.unpack('>f', b[10+i*6 : 14+i*6])[0]
                    
                    # Store as Param_ID (e.g., Param_00d1). 
                    record[f'Param_{param_id:04x}'] = val
                    
                records.append(record)
            except Exception:
                continue
                
        df = pd.DataFrame(records)
        if not df.empty:
            # Clean up: Sort chronologically and drop overlapping timestamps
            df = df.sort_values('Date/Time').drop_duplicates(subset=['Date/Time']).reset_index(drop=True)
        return df
        
    except Exception as e:
        print(f"Error parsing .dat: {e}")
        return pd.DataFrame()

def parse_csv(file_obj):
    """Safely reads CSV event and shutdown logs."""
    try:
        return pd.read_csv(file_obj, encoding='utf-8', on_bad_lines='skip')
    except:
        return pd.DataFrame()
