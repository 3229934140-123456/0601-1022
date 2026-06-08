import csv
import math
import yaml
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any


def read_csv(file_path):
    df = pd.read_csv(file_path, encoding='utf-8')
    return df


def read_excel(file_path, sheet_name=0):
    df = pd.read_excel(file_path, sheet_name=sheet_name, engine='openpyxl')
    return df


def read_file(file_path, sheet_name=0):
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == '.csv':
        return read_csv(path)
    elif suffix in ['.xlsx', '.xls']:
        return read_excel(path, sheet_name)
    else:
        raise ValueError(f"不支持的文件格式: {suffix}")


def write_csv(df, file_path):
    df.to_csv(file_path, index=False, encoding='utf-8-sig')
    return file_path


def write_excel(sheets_dict, file_path):
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        for sheet_name, df in sheets_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    return file_path


def load_yaml(file_path):
    path = Path(file_path)
    if not path.exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def save_yaml(data, file_path):
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return path


def safe_float(value, default=0.0):
    try:
        if value is None or value == '':
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (ValueError, TypeError):
        return default


def format_number(num, decimals=4):
    if abs(num) >= 1000:
        return f"{num:,.{decimals}f}"
    return f"{num:.{decimals}f}"
