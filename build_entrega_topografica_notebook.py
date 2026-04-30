import json
from pathlib import Path


TARGET_NB = Path("entrega_topografica_express_colab.ipynb")


def src(text):
    text = text.strip("\n")
    return [line + "\n" for line in text.splitlines()]


intro_md = r"""
# Entrega Topografica Express

Notebook para Google Colab orientado a topografia basica: subes uno o varios archivos de puntos, revisas columnas, sistema de coordenadas y errores, y despues exportas solamente lo que necesitas.

La herramienta:

- Carga varios archivos `.csv`, `.txt`, `.dat`, `.pts`, `.xlsx` o `.xls`.
- Pregunta si el formato de columnas y el CRS de entrada son iguales para todos.
- Permite configurar archivo por archivo cuando cambia el formato.
- Revisa errores antes de exportar y deja editar o saltar puntos problematicos.
- Transforma coordenadas al CRS de salida elegido.
- Genera curvas de nivel con puntos cuya descripcion contiene `TN`.
- Exporta con botones independientes: `PDF`, `DXF`, `KMZ`, `XLSX` y `HTML`.
- El PDF incluye plano con mapa de fondo, grilla, norte, escala, leyenda, curvas y acotaciones automaticas.
- El HTML incluye mapa interactivo con puntos y curvas generadas.

Formato recomendado:

| Punto | Este / Longitud | Norte / Latitud | Cota | Descripcion |
|---|---:|---:|---:|---|
| 1 | 5489234.22 | 6351234.88 | 122.45 | TN |
| 2 | 5489241.10 | 6351240.02 | 122.31 | BORDE |

Importante: internamente la herramienta trabaja como GIS, es decir, primero `Este/Longitud` y despues `Norte/Latitud`. Si tu libreta viene como `X = Norte` y `Y = Este`, activa la opcion de intercambiar ejes.
"""


install_md = r"""
## 1. Instalar dependencias

Ejecuta esta celda una vez por sesion de Colab.
"""


install_code = r"""
!pip -q install pandas numpy openpyxl pyproj scipy matplotlib ezdxf simplekml folium ipywidgets contextily
"""


helpers_md = r"""
## 2. Funciones de la herramienta

Ejecuta esta celda completa. Define lectura, validacion, revision, transformacion, curvas y exportables.
"""


helpers_code = r"""
from pathlib import Path
from datetime import datetime
import csv
import math
import os
import re
import warnings

import ezdxf
import folium
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.ticker import ScalarFormatter
import numpy as np
import pandas as pd
from pyproj import CRS, Geod, Transformer
from scipy.interpolate import griddata
from scipy.spatial import ConvexHull, QhullError
import simplekml

try:
    import contextily as ctx
except Exception:
    ctx = None

from IPython.display import HTML, IFrame, Markdown, clear_output, display
import ipywidgets as widgets

try:
    from google.colab import files
except Exception:
    files = None


OUTPUT_DIR = Path("/content/entrega_topografica")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


CRS_OPTIONS = [
    ("WGS84 geograficas lat/lon - EPSG:4326", "EPSG:4326"),
    ("WGS84 / UTM 19S - EPSG:32719", "EPSG:32719"),
    ("WGS84 / UTM 20S - EPSG:32720", "EPSG:32720"),
    ("WGS84 / UTM 21S - EPSG:32721", "EPSG:32721"),
    ("POSGAR 2007 / Argentina 1 - EPSG:5343", "EPSG:5343"),
    ("POSGAR 2007 / Argentina 2 - EPSG:5344", "EPSG:5344"),
    ("POSGAR 2007 / Argentina 3 - EPSG:5345", "EPSG:5345"),
    ("POSGAR 2007 / Argentina 4 - EPSG:5346", "EPSG:5346"),
    ("POSGAR 2007 / Argentina 5 - EPSG:5347", "EPSG:5347"),
    ("POSGAR 2007 / Argentina 6 - EPSG:5348", "EPSG:5348"),
    ("POSGAR 2007 / Argentina 7 - EPSG:5349", "EPSG:5349"),
    ("Otro EPSG / PROJ / WKT", "CUSTOM"),
]


CATEGORY_RULES = [
    ("TRAZA_PK", ["PK"], "#d32f2f", 1, "diamond", "http://maps.google.com/mapfiles/kml/paddle/red-diamond.png"),
    ("BERMA", ["BERMA"], "#8d6e63", 30, "square", "http://maps.google.com/mapfiles/kml/paddle/brn-square.png"),
    ("DIQUE", ["DIQUE"], "#00897b", 4, "triangle", "http://maps.google.com/mapfiles/kml/paddle/grn-diamond.png"),
    ("MOJON", ["MOJON", "MOJÓN"], "#3949ab", 5, "target", "http://maps.google.com/mapfiles/kml/shapes/target.png"),
    ("CARTEL", ["CARTEL"], "#f9a825", 2, "square", "http://maps.google.com/mapfiles/kml/shapes/info-i.png"),
    ("SOLDADURA", ["SOLD", "SOLDADURA"], "#ad1457", 6, "x", "http://maps.google.com/mapfiles/kml/paddle/pink-circle.png"),
    ("MUERTO_ANCLAJE", ["MUERTO", "ANCLAJE"], "#5d4037", 30, "diamond", "http://maps.google.com/mapfiles/kml/shapes/caution.png"),
    ("BRIDA", ["BRIDA"], "#e64a19", 1, "circle", "http://maps.google.com/mapfiles/kml/paddle/orange-circle.png"),
    ("PLATINA", ["PLATINA"], "#7b1fa2", 6, "square", "http://maps.google.com/mapfiles/kml/paddle/purple-square.png"),
    ("ESTRELLA", ["ESTRELLA"], "#fbc02d", 2, "target", "http://maps.google.com/mapfiles/kml/paddle/ylw-stars.png"),
    ("TN", ["TN", "TERRENO", "NATURAL", "SUELO"], "#2e7d32", 3, "circle", "http://maps.google.com/mapfiles/kml/paddle/grn-circle.png"),
    ("CONTROL", ["PF", "PUNTO FIJO", "CONTROL", "BASE", "BM", "IGN"], "#c62828", 1, "target", "http://maps.google.com/mapfiles/kml/shapes/target.png"),
    ("EJE", ["EJE", "AXIS", "CENTER", "CENTRO"], "#1565c0", 5, "triangle", "http://maps.google.com/mapfiles/kml/paddle/blu-diamond.png"),
    ("BORDE", ["BORDE", "CORDON", "BANQUINA", "LIMITE"], "#f9a825", 2, "square", "http://maps.google.com/mapfiles/kml/paddle/ylw-square.png"),
    ("ALAMBRADO", ["ALAM", "ALAMBRADO", "CERCO", "TRANQUERA", "VALLA"], "#6d4c41", 30, "x", "http://maps.google.com/mapfiles/kml/shapes/ranger_station.png"),
    ("CONSTRUCCION", ["CONST", "EDIF", "CASA", "MURO", "PARED", "GALPON", "OBRA"], "#00838f", 4, "square", "http://maps.google.com/mapfiles/kml/shapes/homegardenbusiness.png"),
    ("ARBOL", ["ARBOL", "TREE", "VEG", "VEGETACION", "PLANTA"], "#558b2f", 92, "circle", "http://maps.google.com/mapfiles/kml/shapes/parks.png"),
    ("POSTE", ["POSTE", "COLUMNA", "TORRE", "LUMINARIA"], "#6a1b9a", 6, "diamond", "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png"),
    ("CAMINO", ["CALLE", "CAMINO", "RUTA", "PAV", "PAVIMENTO", "HUELLA"], "#424242", 8, "diamond", "http://maps.google.com/mapfiles/kml/paddle/wht-circle.png"),
    ("AGUA", ["AGUA", "CANAL", "ARROYO", "LAGUNA", "CUNETA"], "#0277bd", 5, "circle", "http://maps.google.com/mapfiles/kml/paddle/blu-circle.png"),
]

DEFAULT_CATEGORY = ("OTRO", [], "#616161", 7, "dot", "http://maps.google.com/mapfiles/kml/paddle/wht-blank.png")


def parse_crs(value):
    text = str(value or "").strip()
    if " - " in text and text.upper().startswith("EPSG"):
        text = text.split(" - ", 1)[0].strip()
    if not text or text == "CUSTOM":
        raise ValueError("Indica un sistema de coordenadas valido. Ejemplo: EPSG:5347")
    return CRS.from_user_input(text)


def selected_crs_value(choice, custom):
    choice = str(choice or "").strip()
    custom = str(custom or "").strip()
    return custom if choice == "CUSTOM" else choice


def parse_number(value):
    if value is None:
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    text = str(value).strip().replace(" ", "")
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return np.nan
    text = text.replace("'", "")
    has_comma = "," in text
    has_dot = "." in text
    if has_comma and has_dot:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        text = text.replace(",", ".")
    return float(text)


def is_numeric_like(value):
    try:
        parsed = parse_number(value)
        return np.isfinite(parsed)
    except Exception:
        return False


def numeric_series(series):
    return series.apply(parse_number)


def numeric_ratio(series, max_rows=80):
    sample = series.dropna().head(max_rows)
    if len(sample) == 0:
        return 0.0
    ok = 0
    for value in sample:
        try:
            parsed = parse_number(value)
            if np.isfinite(parsed):
                ok += 1
        except Exception:
            pass
    return ok / len(sample)


def _header_looks_like_data(columns):
    cols = [str(c).strip() for c in columns]
    if not cols:
        return False
    numeric_count = sum(is_numeric_like(c) for c in cols)
    return numeric_count >= max(2, len(cols) // 2)


def read_points_file(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(path)
        if _header_looks_like_data(df.columns):
            df = pd.read_excel(path, header=None)
            df.columns = [f"C{i + 1}" for i in range(len(df.columns))]
        return df

    if suffix not in [".csv", ".txt", ".dat", ".pts"]:
        raise ValueError(f"Formato no soportado: {suffix}. Usa CSV, TXT, DAT, PTS, XLSX o XLS.")

    encodings = ["utf-8-sig", "utf-8", "latin1", "cp1252"]
    last_error = None
    for enc in encodings:
        try:
            df = pd.read_csv(path, sep=None, engine="python", encoding=enc, quoting=csv.QUOTE_NONE)
            if len(df.columns) == 1:
                for sep in [";", ",", "\t", r"\s+"]:
                    df = pd.read_csv(path, sep=sep, engine="python", encoding=enc, quoting=csv.QUOTE_NONE)
                    if len(df.columns) > 1:
                        break
            if _header_looks_like_data(df.columns):
                df = pd.read_csv(path, sep=None, engine="python", encoding=enc, header=None, quoting=csv.QUOTE_NONE)
                if len(df.columns) == 1:
                    for sep in [";", ",", "\t", r"\s+"]:
                        df = pd.read_csv(path, sep=sep, engine="python", encoding=enc, header=None, quoting=csv.QUOTE_NONE)
                        if len(df.columns) > 1:
                            break
                df.columns = [f"C{i + 1}" for i in range(len(df.columns))]
            return df
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"No pude leer el archivo. Ultimo error: {last_error}")


def normalize_col_name(name):
    text = str(name).strip().upper()
    replacements = {"Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ñ": "N"}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"[^A-Z0-9]+", "", text)


def guess_column(df, candidates):
    normalized = {normalize_col_name(c): c for c in df.columns}
    for cand in candidates:
        key = normalize_col_name(cand)
        if key in normalized:
            return normalized[key]
    for col in df.columns:
        ncol = normalize_col_name(col)
        if any(normalize_col_name(cand) in ncol for cand in candidates):
            return col
    return df.columns[0] if len(df.columns) else None


def is_generic_columns(df):
    return all(re.fullmatch(r"C\d+", str(col)) for col in df.columns)


def infer_crs_and_axis(col_a, col_b):
    a = pd.to_numeric(col_a.apply(parse_number), errors="coerce").dropna()
    b = pd.to_numeric(col_b.apply(parse_number), errors="coerce").dropna()
    if a.empty or b.empty:
        return {"input_crs": "EPSG:5344", "axis_order": "unknown", "confidence": "baja", "note": "No hay suficientes coordenadas numericas para detectar CRS."}

    ma = float(a.median())
    mb = float(b.median())
    aa = abs(ma)
    ab = abs(mb)

    if aa <= 180 and ab <= 90:
        return {"input_crs": "EPSG:4326", "axis_order": "east_north", "confidence": "alta", "note": "Parece longitud/latitud WGS84."}
    if aa <= 90 and ab <= 180:
        return {"input_crs": "EPSG:4326", "axis_order": "north_east", "confidence": "alta", "note": "Parece latitud/longitud WGS84."}

    def gk_zone(value):
        zone = int(abs(value) // 1_000_000)
        return zone if 1 <= zone <= 7 else None

    zone_b = gk_zone(mb)
    if 5_000_000 <= aa <= 7_500_000 and zone_b:
        return {
            "input_crs": f"EPSG:{5342 + zone_b}",
            "axis_order": "north_east",
            "confidence": "alta",
            "note": f"Detectado POSGAR 2007 / Argentina {zone_b}: primera coordenada Norte, segunda Este.",
        }

    zone_a = gk_zone(ma)
    if 5_000_000 <= ab <= 7_500_000 and zone_a:
        return {
            "input_crs": f"EPSG:{5342 + zone_a}",
            "axis_order": "east_north",
            "confidence": "alta",
            "note": f"Detectado POSGAR 2007 / Argentina {zone_a}: primera coordenada Este, segunda Norte.",
        }

    if 120_000 <= aa <= 900_000 and 0 <= ab <= 10_000_000:
        return {"input_crs": "EPSG:32720", "axis_order": "east_north", "confidence": "media", "note": "Parece UTM sur. Confirma la zona EPSG."}
    if 120_000 <= ab <= 900_000 and 0 <= aa <= 10_000_000:
        return {"input_crs": "EPSG:32720", "axis_order": "north_east", "confidence": "media", "note": "Parece UTM sur con Norte/Este. Confirma la zona EPSG."}

    return {"input_crs": "EPSG:5344", "axis_order": "unknown", "confidence": "baja", "note": "No pude detectar el CRS con seguridad. Revisa EPSG y orden de ejes."}


def auto_detect_file_config(file_item):
    df = file_item["df"]
    cols = list(df.columns)
    detection = {
        "archivo": file_item["name"],
        "point_col": None,
        "x_col": None,
        "y_col": None,
        "z_col": None,
        "desc_col": None,
        "swap_xy": False,
        "input_crs": "EPSG:5344",
        "organization": "custom",
        "confidence": "baja",
        "note": "Deteccion pendiente.",
    }
    if len(cols) >= 5 and is_generic_columns(df):
        detection.update({"point_col": cols[0], "z_col": cols[3], "desc_col": cols[4]})
        axis = infer_crs_and_axis(df[cols[1]], df[cols[2]])
        detection.update({"input_crs": axis["input_crs"], "confidence": axis["confidence"], "note": axis["note"]})
        if axis["axis_order"] == "north_east":
            detection.update({"x_col": cols[2], "y_col": cols[1], "organization": "northing_first"})
        else:
            detection.update({"x_col": cols[1], "y_col": cols[2], "organization": "standard"})
        return detection

    point_col = guess_column(df, ["PTO", "PUNTO", "POINT", "ID", "NRO", "NUMERO", "Column1"])
    z_col = guess_column(df, ["Z", "COTA", "ELEV", "ELEVACION", "ALTURA", "ALT", "Column4"])
    desc_col = guess_column(df, ["DESC", "DESCRIPCION", "CODIGO", "CODE", "OBS", "DETALLE", "Column5"])

    numeric_cols = [col for col in cols if numeric_ratio(df[col]) >= 0.7]
    coord_candidates = [col for col in numeric_cols if col != z_col]
    if point_col in coord_candidates and len(coord_candidates) > 2:
        coord_candidates.remove(point_col)
    if len(coord_candidates) >= 2:
        a_col, b_col = coord_candidates[0], coord_candidates[1]
        axis = infer_crs_and_axis(df[a_col], df[b_col])
        detection.update({"input_crs": axis["input_crs"], "confidence": axis["confidence"], "note": axis["note"]})
        if axis["axis_order"] == "north_east":
            x_col, y_col, org = b_col, a_col, "northing_first"
        else:
            x_col, y_col, org = a_col, b_col, "standard"
    else:
        x_col = guess_column(df, ["ESTE", "EAST", "EASTING", "E", "LONGITUD", "LON", "X", "Column3"])
        y_col = guess_column(df, ["NORTE", "NORTH", "NORTHING", "N", "LATITUD", "LAT", "Y", "Column2"])
        org = "custom"

    detection.update({
        "point_col": point_col,
        "x_col": x_col,
        "y_col": y_col,
        "z_col": z_col,
        "desc_col": desc_col,
        "organization": org,
    })
    return detection


def detection_summary(file_items):
    rows = []
    for item in file_items:
        det = auto_detect_file_config(item)
        rows.append({
            "archivo": item["name"],
            "CRS detectado": det["input_crs"],
            "organizacion": det["organization"],
            "Este/Lon": det["x_col"],
            "Norte/Lat": det["y_col"],
            "Z": det["z_col"],
            "descripcion": det["desc_col"],
            "confianza": det["confidence"],
            "nota": det["note"],
        })
    return pd.DataFrame(rows)


def resolve_col_by_position(base_df, target_df, base_col):
    if base_col is None:
        return None
    if base_col in target_df.columns:
        return base_col
    if base_col in base_df.columns:
        idx = list(base_df.columns).index(base_col)
        if idx < len(target_df.columns):
            return target_df.columns[idx]
    return None


def get_cell(row, col):
    if col is None or col not in row.index:
        return ""
    value = row[col]
    if pd.isna(value):
        return ""
    return value


def classify_description(desc):
    text = str(desc or "").strip().strip('"').upper()
    text_norm = re.sub(r"\s+", "", text)
    if re.match(r"^PK\d+/", text_norm):
        name, color, aci, marker, icon = ("TRAZA_PK", "#d32f2f", 1, "diamond", "http://maps.google.com/mapfiles/kml/paddle/red-diamond.png")
        return {"categoria": name, "color": color, "aci": aci, "marker": marker, "icon": icon}
    for name, keywords, color, aci, marker, icon in CATEGORY_RULES:
        if any(keyword in text for keyword in keywords):
            return {"categoria": name, "color": color, "aci": aci, "marker": marker, "icon": icon}
    name, keywords, color, aci, marker, icon = DEFAULT_CATEGORY
    return {"categoria": name, "color": color, "aci": aci, "marker": marker, "icon": icon}


def apply_review_to_df(df, cfg, file_name, review_state):
    df2 = df.copy()
    df2["_source_row"] = np.arange(1, len(df2) + 1)
    skipped = set(review_state.get("skipped", {}).get(file_name, set())) if review_state else set()
    if skipped:
        df2 = df2[~df2["_source_row"].isin(skipped)].copy()

    edits = review_state.get("edits", {}).get(file_name, {}) if review_state else {}
    logical_to_col = {
        "punto": cfg.get("point_col"),
        "x": cfg.get("x_col"),
        "y": cfg.get("y_col"),
        "z": cfg.get("z_col"),
        "descripcion": cfg.get("desc_col"),
    }
    for row_no, values in edits.items():
        mask = df2["_source_row"] == int(row_no)
        for logical, col in logical_to_col.items():
            if col is not None and col in df2.columns and logical in values:
                df2.loc[mask, col] = values[logical]
    return df2


def validate_configured_file(file_item, cfg, review_state=None):
    df = file_item["df"]
    file_name = file_item["name"]
    skipped = set(review_state.get("skipped", {}).get(file_name, set())) if review_state else set()
    edits = review_state.get("edits", {}).get(file_name, {}) if review_state else {}
    records = []

    required_cols = [("Este/Longitud", cfg.get("x_col")), ("Norte/Latitud", cfg.get("y_col"))]
    for label, col in required_cols:
        if col is None or col not in df.columns:
            records.append({
                "archivo": file_name,
                "fila": 0,
                "severidad": "ERROR",
                "campo": label,
                "problema": f"No se selecciono columna para {label}.",
                "valor": "",
            })

    if any(r["fila"] == 0 for r in records):
        return pd.DataFrame(records)

    for idx, row in df.iterrows():
        row_no = int(idx) + 1
        if row_no in skipped:
            continue

        values = edits.get(row_no, {})
        x_raw = values.get("x", get_cell(row, cfg.get("x_col")))
        y_raw = values.get("y", get_cell(row, cfg.get("y_col")))
        z_raw = values.get("z", get_cell(row, cfg.get("z_col"))) if cfg.get("z_col") else ""
        desc_raw = values.get("descripcion", get_cell(row, cfg.get("desc_col"))) if cfg.get("desc_col") else ""

        try:
            x_val = parse_number(x_raw)
        except Exception:
            x_val = np.nan
        try:
            y_val = parse_number(y_raw)
        except Exception:
            y_val = np.nan

        if not np.isfinite(x_val):
            records.append({"archivo": file_name, "fila": row_no, "severidad": "ERROR", "campo": "Este/Longitud", "problema": "Coordenada no numerica o vacia.", "valor": x_raw})
        if not np.isfinite(y_val):
            records.append({"archivo": file_name, "fila": row_no, "severidad": "ERROR", "campo": "Norte/Latitud", "problema": "Coordenada no numerica o vacia.", "valor": y_raw})

        if cfg.get("z_col") and str(z_raw).strip() != "":
            try:
                parse_number(z_raw)
            except Exception:
                records.append({"archivo": file_name, "fila": row_no, "severidad": "ERROR", "campo": "Z/Cota", "problema": "Cota no numerica.", "valor": z_raw})

        if cfg.get("desc_col") and str(desc_raw).strip() == "":
            records.append({"archivo": file_name, "fila": row_no, "severidad": "AVISO", "campo": "Descripcion", "problema": "Descripcion vacia.", "valor": desc_raw})

    return pd.DataFrame(records)


def standardize_points(file_item, cfg, review_state=None):
    df = apply_review_to_df(file_item["df"], cfg, file_item["name"], review_state)
    out = pd.DataFrame()
    out["source_file"] = file_item["name"]
    out["source_row"] = df["_source_row"].astype(int)
    out["punto"] = df[cfg["point_col"]].astype(str).str.strip() if cfg.get("point_col") else out["source_row"].astype(str)
    out["x_in"] = numeric_series(df[cfg["x_col"]])
    out["y_in"] = numeric_series(df[cfg["y_col"]])
    out["z"] = numeric_series(df[cfg["z_col"]]) if cfg.get("z_col") else np.nan
    out["descripcion"] = df[cfg["desc_col"]].astype(str).str.strip() if cfg.get("desc_col") else ""

    if cfg.get("swap_xy"):
        out[["x_in", "y_in"]] = out[["y_in", "x_in"]]

    before = len(out)
    out = out.dropna(subset=["x_in", "y_in"]).copy()
    dropped = before - len(out)
    classed = out["descripcion"].apply(classify_description).apply(pd.Series)
    out = pd.concat([out.reset_index(drop=True), classed.reset_index(drop=True)], axis=1)
    return out, dropped


def transform_points(points, input_crs, output_crs):
    transformed = points.copy()
    if input_crs == output_crs:
        transformed["x"] = transformed["x_in"]
        transformed["y"] = transformed["y_in"]
        transformed["transformacion"] = "Sin transformacion"
        return transformed
    transformer = Transformer.from_crs(input_crs, output_crs, always_xy=True)
    x_out, y_out = transformer.transform(transformed["x_in"].to_numpy(), transformed["y_in"].to_numpy())
    transformed["x"] = x_out
    transformed["y"] = y_out
    transformed["transformacion"] = f"{input_crs.to_string()} -> {output_crs.to_string()}"
    return transformed


def quality_checks(points, dropped_rows):
    checks = []
    checks.append(("Puntos validos", len(points)))
    checks.append(("Filas descartadas por X/Y invalido", int(dropped_rows)))
    checks.append(("Puntos sin cota Z", int(points["z"].isna().sum())))
    checks.append(("Puntos sin descripcion", int((points["descripcion"].astype(str).str.strip() == "").sum())))
    checks.append(("Coordenadas X/Y duplicadas exactas", int(points.duplicated(subset=["x", "y"], keep=False).sum())))

    if len(points) >= 5:
        cx, cy = points["x"].mean(), points["y"].mean()
        dist = np.hypot(points["x"] - cx, points["y"] - cy)
        q1, q3 = np.nanpercentile(dist, [25, 75])
        threshold = q3 + 3 * (q3 - q1)
        checks.append(("Posibles puntos alejados", int((dist > threshold).sum())))
    else:
        checks.append(("Posibles puntos alejados", 0))

    tn_count = int(points["descripcion"].str.contains(r"\bTN\b", case=False, regex=True, na=False).sum())
    checks.append(("Puntos TN para curvas", tn_count))

    if len(points):
        checks.append(("Extension X", float(points["x"].max() - points["x"].min())))
        checks.append(("Extension Y", float(points["y"].max() - points["y"].min())))
    return pd.DataFrame(checks, columns=["control", "valor"])


def create_contours(points, interval, tn_pattern=r"\bTN\b", max_grid=240):
    if interval is None or interval <= 0:
        return [], "Equidistancia invalida. No se generaron curvas."
    tn = points[points["descripcion"].str.contains(tn_pattern, case=False, regex=True, na=False)].copy()
    tn = tn.dropna(subset=["x", "y", "z"])
    if len(tn) < 3:
        return [], "No hay suficientes puntos TN con Z para generar curvas."
    if tn["z"].max() - tn["z"].min() < interval:
        return [], "El rango de cotas TN es menor que la equidistancia seleccionada."

    x = tn["x"].to_numpy(float)
    y = tn["y"].to_numpy(float)
    z = tn["z"].to_numpy(float)
    width = max(x.max() - x.min(), 1.0)
    height = max(y.max() - y.min(), 1.0)
    n = min(max_grid, max(80, int(math.sqrt(len(tn)) * 12)))
    nx = n
    ny = max(50, int(n * height / width)) if width >= height else n
    nx = max(50, int(n * width / height)) if height > width else nx
    nx = min(max_grid, nx)
    ny = min(max_grid, ny)

    gx, gy = np.meshgrid(np.linspace(x.min(), x.max(), nx), np.linspace(y.min(), y.max(), ny))
    try:
        gz = griddata((x, y), z, (gx, gy), method="linear")
    except QhullError:
        return [], "Los puntos TN parecen colineales. No se puede triangular una superficie."

    if np.all(np.isnan(gz)):
        return [], "No se pudo interpolar superficie con los puntos TN."

    zmin = math.floor(np.nanmin(z) / interval) * interval
    zmax = math.ceil(np.nanmax(z) / interval) * interval
    levels = np.arange(zmin, zmax + interval * 0.5, interval)
    levels = levels[(levels >= np.nanmin(z)) & (levels <= np.nanmax(z))]
    if len(levels) == 0:
        return [], "No hay niveles de curva dentro del rango de cotas."

    fig, ax = plt.subplots()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cs = ax.contour(gx, gy, gz, levels=levels)

    contours = []
    for level, segments in zip(cs.levels, cs.allsegs):
        for seg in segments:
            if len(seg) >= 2:
                coords = [(float(px), float(py)) for px, py in seg]
                contours.append({"level": float(level), "coords": coords})
    plt.close(fig)
    return contours, f"Curvas generadas: {len(contours)} segmentos en {len(levels)} niveles."


def parse_pk_descriptor(desc):
    text = str(desc or "").strip().strip('"').upper().replace(" ", "")
    match = re.match(r"^(PK\d+)/(.*)$", text)
    if not match:
        return None
    pk = match.group(1)
    suffix = match.group(2)
    order_match = re.search(r"(\d+)", suffix)
    order = int(order_match.group(1)) if order_match else 0
    return {"group": pk, "suffix": suffix, "order": order}


def build_feature_lines(points):
    lines = []
    if points.empty:
        return lines

    pk_rows = []
    for idx, row in points.iterrows():
        parsed = parse_pk_descriptor(row.get("descripcion", ""))
        if parsed:
            pk_rows.append({
                "idx": idx,
                "source_file": row["source_file"],
                "group": parsed["group"],
                "order": parsed["order"],
                "source_row": row["source_row"],
                "x": float(row["x"]),
                "y": float(row["y"]),
                "z": None if pd.isna(row["z"]) else float(row["z"]),
            })

    if pk_rows:
        pk_df = pd.DataFrame(pk_rows)
        for (source_file, group), g in pk_df.groupby(["source_file", "group"], sort=False):
            g = g.sort_values(["order", "source_row"])
            if len(g) >= 2:
                coords = [(float(r.x), float(r.y), r.z) for r in g.itertuples(index=False)]
                lines.append({
                    "name": f"{Path(source_file).stem} - {group}",
                    "category": "TRAZA_PK",
                    "layer": f"LINEA_{group}",
                    "color": "#d32f2f",
                    "aci": 1,
                    "coords": coords,
                    "closed": False,
                })

    berma = points[points["categoria"] == "BERMA"].copy()
    if not berma.empty:
        for (source_file, desc), g in berma.groupby(["source_file", "descripcion"], sort=False):
            if len(g) >= 3:
                g = g.sort_values("source_row")
                coords = [(float(r.x), float(r.y), None if pd.isna(r.z) else float(r.z)) for r in g.itertuples(index=False)]
                lines.append({
                    "name": f"{desc}",
                    "category": "BERMA",
                    "layer": "LINEA_BERMA",
                    "color": "#8d6e63",
                    "aci": 30,
                    "coords": coords,
                    "closed": True,
                })

    dique_rows = []
    for _, row in points[points["categoria"] == "DIQUE"].iterrows():
        text = str(row["descripcion"]).upper()
        match = re.search(r"DIQUE\s*(\d+)", text)
        if match:
            dique_rows.append({
                "source_file": row["source_file"],
                "group": f"DIQUE_{match.group(1)}",
                "source_row": row["source_row"],
                "x": float(row["x"]),
                "y": float(row["y"]),
                "z": None if pd.isna(row["z"]) else float(row["z"]),
            })
    if dique_rows:
        dique_df = pd.DataFrame(dique_rows)
        for (source_file, group), g in dique_df.groupby(["source_file", "group"], sort=False):
            if len(g) >= 2:
                g = g.sort_values("source_row")
                coords = [(float(r.x), float(r.y), r.z) for r in g.itertuples(index=False)]
                lines.append({
                    "name": group.replace("_", " "),
                    "category": "DIQUE",
                    "layer": "LINEA_DIQUE",
                    "color": "#00897b",
                    "aci": 4,
                    "coords": coords,
                    "closed": False,
                })
    return lines


def nice_number(value):
    if value <= 0 or not np.isfinite(value):
        return 1.0
    exponent = math.floor(math.log10(value))
    fraction = value / (10 ** exponent)
    if fraction < 1.5:
        nice = 1
    elif fraction < 3:
        nice = 2
    elif fraction < 7:
        nice = 5
    else:
        nice = 10
    return nice * (10 ** exponent)


def distance_label(p1, p2, crs):
    if crs.is_geographic:
        geod = Geod(ellps="WGS84")
        _, _, dist = geod.inv(p1[0], p1[1], p2[0], p2[1])
    else:
        dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if dist >= 1000:
        return f"{dist / 1000:.3f} km"
    return f"{dist:.2f} m"


def make_distance_annotations(points, crs):
    if points.empty:
        return []
    minx, maxx = points["x"].min(), points["x"].max()
    miny, maxy = points["y"].min(), points["y"].max()
    width = maxx - minx
    height = maxy - miny
    span = max(width, height, 1.0)
    margin = span * 0.06
    annotations = []

    if width > 0:
        p1 = (minx, miny - margin)
        p2 = (maxx, miny - margin)
        annotations.append({"p1": p1, "p2": p2, "label": "Ancho relevado " + distance_label((minx, miny), (maxx, miny), crs)})

    if height > 0:
        p1 = (maxx + margin, miny)
        p2 = (maxx + margin, maxy)
        annotations.append({"p1": p1, "p2": p2, "label": "Alto relevado " + distance_label((maxx, miny), (maxx, maxy), crs)})

    coords = points[["x", "y"]].dropna().to_numpy(float)
    if len(coords) >= 2:
        pair = None
        max_dist = -1
        try:
            hull = ConvexHull(coords)
            candidates = coords[hull.vertices]
        except Exception:
            candidates = coords
        if len(candidates) > 80:
            candidates = candidates[np.linspace(0, len(candidates) - 1, 80).astype(int)]
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                dist = float(np.sum((candidates[i] - candidates[j]) ** 2))
                if dist > max_dist:
                    max_dist = dist
                    pair = (tuple(candidates[i]), tuple(candidates[j]))
        if pair:
            annotations.append({"p1": pair[0], "p2": pair[1], "label": "Mayor diagonal " + distance_label(pair[0], pair[1], crs)})
    return annotations[:3]


def apply_axis_style(ax):
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, color="#111111", linewidth=0.35, alpha=0.38)
    ax.tick_params(axis="both", labelsize=8)
    ax.xaxis.set_major_formatter(ScalarFormatter(useOffset=False))
    ax.yaxis.set_major_formatter(ScalarFormatter(useOffset=False))
    ax.ticklabel_format(style="plain", axis="both", useOffset=False)


def add_background_map(ax, output_crs, use_basemap=True, provider_name="OpenStreetMap"):
    if not use_basemap:
        return "Mapa base desactivado."
    if ctx is None:
        return "contextily no esta disponible; se omitio mapa base."
    try:
        provider = ctx.providers.OpenStreetMap.Mapnik
        if provider_name == "CartoDB Positron":
            provider = ctx.providers.CartoDB.Positron
        elif provider_name == "CartoDB Voyager":
            provider = ctx.providers.CartoDB.Voyager
        ctx.add_basemap(
            ax,
            crs=output_crs.to_string(),
            source=provider,
            reset_extent=True,
            attribution_size=5,
            alpha=0.72,
            zorder=0,
        )
        return "Mapa base agregado."
    except Exception as exc:
        ax.text(
            0.02,
            0.02,
            f"Mapa base no disponible: {exc}",
            transform=ax.transAxes,
            fontsize=7,
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#777777"},
        )
        return f"Mapa base no disponible: {exc}"


def plot_marker(ax, x, y, marker, color, size=28, label=None):
    mpl_marker = {
        "circle": "o",
        "square": "s",
        "triangle": "^",
        "diamond": "D",
        "x": "x",
        "target": "P",
        "dot": ".",
    }.get(marker, "o")
    ax.scatter([x], [y], s=size, marker=mpl_marker, color=color, edgecolors="black", linewidths=0.35, label=label, zorder=4)


def make_plan_figure(points, contours, feature_lines, annotations, output_crs, project_name, interval, label_points=True, use_basemap=True, basemap_provider="OpenStreetMap"):
    fig, ax = plt.subplots(figsize=(16.5, 11.7))

    minx, maxx = points["x"].min(), points["x"].max()
    miny, maxy = points["y"].min(), points["y"].max()
    span = max(maxx - minx, maxy - miny, 1.0)
    ax.set_xlim(minx - span * 0.12, maxx + span * 0.16)
    ax.set_ylim(miny - span * 0.12, maxy + span * 0.14)
    add_background_map(ax, output_crs, use_basemap, basemap_provider)

    if contours:
        major_step = interval * 5 if interval else None
        for contour in contours:
            coords = np.array(contour["coords"], dtype=float)
            if len(coords) < 2:
                continue
            level = contour["level"]
            is_major = bool(major_step and abs((level / major_step) - round(level / major_step)) < 1e-6)
            color = "#4e342e" if is_major else "#795548"
            lw = 1.15 if is_major else 0.6
            ax.plot(coords[:, 0], coords[:, 1], color=color, linewidth=lw, zorder=2.5)
            if is_major and len(coords) > 6:
                mid = coords[len(coords) // 2]
                ax.text(mid[0], mid[1], f"{level:.2f}", fontsize=6, color=color, ha="center", va="center", bbox={"facecolor": "white", "alpha": 0.72, "edgecolor": "none", "pad": 0.5}, zorder=5)

    for line in feature_lines:
        coords = np.array([(pt[0], pt[1]) for pt in line["coords"]], dtype=float)
        if len(coords) < 2:
            continue
        if line.get("closed") and len(coords) >= 3:
            coords = np.vstack([coords, coords[0]])
        lw = 1.6 if line["category"] == "TRAZA_PK" else 1.05
        ax.plot(coords[:, 0], coords[:, 1], color=line["color"], linewidth=lw, zorder=3.2, label=line["category"] if line["category"] not in ax.get_legend_handles_labels()[1] else None)

    for _, group in points.groupby("categoria"):
        first = group.iloc[0]
        label = first["categoria"]
        for idx, row in group.iterrows():
            plot_marker(ax, row["x"], row["y"], row["marker"], row["color"], label=label if idx == group.index[0] else None)

    if label_points:
        max_labels = 350
        sample = points if len(points) <= max_labels else points.iloc[np.linspace(0, len(points) - 1, max_labels).astype(int)]
        dx = max(points["x"].max() - points["x"].min(), 1.0) * 0.003
        dy = max(points["y"].max() - points["y"].min(), 1.0) * 0.003
        for _, row in sample.iterrows():
            ztxt = "" if pd.isna(row["z"]) else f" {row['z']:.2f}"
            ax.text(row["x"] + dx, row["y"] + dy, f"{row['punto']}{ztxt}", fontsize=5.8, color="#111111", zorder=5, bbox={"facecolor": "white", "alpha": 0.38, "edgecolor": "none", "pad": 0.2})

    for ann in annotations:
        p1, p2, label = ann["p1"], ann["p2"], ann["label"]
        ax.annotate("", xy=p2, xytext=p1, arrowprops={"arrowstyle": "<->", "color": "#111111", "lw": 0.9}, zorder=6)
        mx = (p1[0] + p2[0]) / 2
        my = (p1[1] + p2[1]) / 2
        ax.text(mx, my, label, fontsize=8, ha="center", va="bottom", bbox={"facecolor": "white", "edgecolor": "#777777", "alpha": 0.9, "pad": 2}, zorder=7)

    apply_axis_style(ax)
    ax.set_xlabel("Este / Longitud")
    ax.set_ylabel("Norte / Latitud")
    ax.annotate("N", xy=(0.94, 0.93), xytext=(0.94, 0.82), xycoords="axes fraction", textcoords="axes fraction", ha="center", va="center", fontsize=18, fontweight="bold", arrowprops={"arrowstyle": "-|>", "lw": 1.8, "color": "#111111"})

    if output_crs.is_projected:
        bar = nice_number(span / 5)
        x0 = minx + span * 0.03
        y0 = miny + span * 0.035
        ax.plot([x0, x0 + bar], [y0, y0], color="black", linewidth=3, zorder=8)
        ax.plot([x0, x0], [y0 - span * 0.005, y0 + span * 0.005], color="black", linewidth=1, zorder=8)
        ax.plot([x0 + bar, x0 + bar], [y0 - span * 0.005, y0 + span * 0.005], color="black", linewidth=1, zorder=8)
        ax.text(x0 + bar / 2, y0 + span * 0.01, f"{bar:g} m", fontsize=8, ha="center", bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"}, zorder=8)
    else:
        ax.text(0.02, 0.03, "CRS geografico: escala grafica omitida", transform=ax.transAxes, fontsize=8, bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "#999999"}, zorder=8)

    ax.legend(loc="upper left", fontsize=8, frameon=True)
    title = project_name.strip() or "Entrega topografica"
    ax.set_title(title, fontsize=16, fontweight="bold", pad=12)

    info = [
        f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"CRS salida: {output_crs.to_string()}",
        f"Puntos: {len(points)}",
        f"Polilineas: {len(feature_lines)}",
        f"Curvas: {'si' if contours else 'no'}",
        f"Equidistancia: {interval:g} m" if contours else "Equidistancia: sin curvas",
    ]
    fig.text(0.72, 0.03, "\n".join(info), fontsize=8, ha="left", va="bottom", bbox={"facecolor": "white", "edgecolor": "#333333", "pad": 5})
    fig.tight_layout(rect=[0.02, 0.06, 0.98, 0.96])
    return fig


def build_pdf_report(pdf_path, result):
    points = result["points"]
    with PdfPages(pdf_path) as pdf:
        fig = make_plan_figure(
            points,
            result["contours"],
            result["feature_lines"],
            result["annotations"],
            result["output_crs"],
            result["project_name"],
            result["interval"],
            result["label_points"],
            result["use_basemap"],
            result["basemap_provider"],
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        ax.axis("off")
        ax.text(0.03, 0.95, result["project_name"], fontsize=18, fontweight="bold", transform=ax.transAxes)
        ax.text(0.03, 0.90, "Resumen tecnico y controles automaticos", fontsize=12, transform=ax.transAxes)
        ax.text(0.03, 0.85, f"CRS salida: {result['output_crs'].to_string()}", fontsize=9, transform=ax.transAxes)
        counts = points["categoria"].value_counts().rename_axis("categoria").reset_index(name="cantidad")

        qc_table = result["qc"].copy()
        qc_table["valor"] = qc_table["valor"].apply(lambda v: f"{v:.3f}" if isinstance(v, float) and abs(v) >= 1 else str(v))
        table1 = ax.table(cellText=qc_table.values, colLabels=qc_table.columns, cellLoc="left", colLoc="left", bbox=[0.03, 0.42, 0.45, 0.36])
        table1.auto_set_font_size(False)
        table1.set_fontsize(8)
        table2 = ax.table(cellText=counts.values, colLabels=counts.columns, cellLoc="left", colLoc="left", bbox=[0.53, 0.42, 0.38, 0.36])
        table2.auto_set_font_size(False)
        table2.set_fontsize(8)

        notes = [
            "Notas:",
            "- Las curvas se interpolan solo con puntos cuya descripcion contiene TN.",
            "- Las acotaciones son automaticas: ancho, alto y mayor diagonal del relevamiento.",
            "- El mapa base es referencial; verificar CRS, zona y unidades antes de entregar.",
        ]
        ax.text(0.03, 0.25, "\n".join(notes), fontsize=9, transform=ax.transAxes, va="top")
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        preview_cols = ["source_file", "punto", "x", "y", "z", "descripcion", "categoria"]
        preview = points[preview_cols].head(45).copy()
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        ax.axis("off")
        ax.text(0.03, 0.95, "Primeros puntos procesados", fontsize=14, fontweight="bold", transform=ax.transAxes)
        table = ax.table(cellText=preview.round(3).astype(str).values, colLabels=preview.columns, cellLoc="left", colLoc="left", bbox=[0.02, 0.05, 0.96, 0.84])
        table.auto_set_font_size(False)
        table.set_fontsize(6.2)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def format_z(value, decimals=3):
    if pd.isna(value):
        return ""
    return f"{float(value):.{decimals}f}"


def draw_dxf_marker(msp, x, y, z, marker, size, layer):
    attrs = {"layer": layer}
    if marker == "circle":
        msp.add_circle((x, y, z), radius=size * 0.45, dxfattribs=attrs)
    elif marker == "square":
        pts = [(x - size / 2, y - size / 2), (x + size / 2, y - size / 2), (x + size / 2, y + size / 2), (x - size / 2, y + size / 2)]
        msp.add_lwpolyline(pts, close=True, dxfattribs=attrs)
    elif marker == "triangle":
        pts = [(x, y + size / 2), (x - size / 2, y - size / 2), (x + size / 2, y - size / 2)]
        msp.add_lwpolyline(pts, close=True, dxfattribs=attrs)
    elif marker == "diamond":
        pts = [(x, y + size / 2), (x + size / 2, y), (x, y - size / 2), (x - size / 2, y)]
        msp.add_lwpolyline(pts, close=True, dxfattribs=attrs)
    elif marker == "target":
        msp.add_circle((x, y, z), radius=size * 0.55, dxfattribs=attrs)
        msp.add_circle((x, y, z), radius=size * 0.22, dxfattribs=attrs)
        msp.add_line((x - size * 0.7, y, z), (x + size * 0.7, y, z), dxfattribs=attrs)
        msp.add_line((x, y - size * 0.7, z), (x, y + size * 0.7, z), dxfattribs=attrs)
    elif marker == "x":
        msp.add_line((x - size / 2, y - size / 2, z), (x + size / 2, y + size / 2, z), dxfattribs=attrs)
        msp.add_line((x - size / 2, y + size / 2, z), (x + size / 2, y - size / 2, z), dxfattribs=attrs)
    else:
        msp.add_circle((x, y, z), radius=size * 0.18, dxfattribs=attrs)


def add_dxf_text(msp, text, x, y, z, height, layer):
    entity = msp.add_text(str(text), dxfattribs={"layer": layer, "height": height})
    entity.dxf.insert = (x, y, z)


def export_dxf(path, result):
    points = result["points"]
    contours = result["contours"]
    feature_lines = result["feature_lines"]
    annotations = result["annotations"]
    interval = result["interval"]
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()

    for _, row in points.drop_duplicates("categoria").iterrows():
        layer_name = f"PUNTOS_{row['categoria']}"
        if layer_name not in doc.layers:
            doc.layers.add(layer_name, color=int(row["aci"]))
    for layer_name, color in [("CURVAS_NIVEL", 34), ("CURVAS_MAESTRAS", 32), ("LINEA_PK", 1), ("LINEA_BERMA", 30), ("LINEA_DIQUE", 4), ("TEXTOS", 7), ("COTAS", 1)]:
        if layer_name not in doc.layers:
            doc.layers.add(layer_name, color=color)

    span = max(points["x"].max() - points["x"].min(), points["y"].max() - points["y"].min(), 1.0)
    marker_size = max(span / 320, 0.25)
    text_height = max(marker_size * 0.9, 0.18)

    for _, row in points.iterrows():
        z = 0 if pd.isna(row["z"]) else float(row["z"])
        layer = f"PUNTOS_{row['categoria']}"
        draw_dxf_marker(msp, float(row["x"]), float(row["y"]), z, row["marker"], marker_size, layer)
        if result["label_points"]:
            label = str(row["punto"])
            if not pd.isna(row["z"]):
                label += f" / {row['z']:.2f}"
            add_dxf_text(msp, label, float(row["x"]) + marker_size * 0.75, float(row["y"]) + marker_size * 0.75, z, text_height, "TEXTOS")

    major_step = interval * 5 if interval else None
    for contour in contours:
        coords = contour["coords"]
        if len(coords) < 2:
            continue
        level = float(contour["level"])
        is_major = bool(major_step and abs((level / major_step) - round(level / major_step)) < 1e-6)
        layer = "CURVAS_MAESTRAS" if is_major else "CURVAS_NIVEL"
        pts = [(float(x), float(y), level) for x, y in coords]
        msp.add_polyline3d(pts, dxfattribs={"layer": layer})
        if is_major and len(pts) > 6:
            mid = pts[len(pts) // 2]
            add_dxf_text(msp, f"{level:.2f}", mid[0], mid[1], level, text_height * 0.85, layer)

    for line in feature_lines:
        layer = "LINEA_PK" if line["category"] == "TRAZA_PK" else line.get("layer", "LINEA_PK")
        if layer not in doc.layers:
            doc.layers.add(layer, color=int(line.get("aci", 7)))
        pts = [(float(x), float(y), 0 if z is None else float(z)) for x, y, z in line["coords"]]
        if line.get("closed") and len(pts) >= 3:
            pts = pts + [pts[0]]
        if len(pts) >= 2:
            msp.add_polyline3d(pts, dxfattribs={"layer": layer})
            mid = pts[len(pts) // 2]
            add_dxf_text(msp, line["name"], mid[0], mid[1], mid[2], text_height, layer)

    for ann in annotations:
        p1, p2, label = ann["p1"], ann["p2"], ann["label"]
        msp.add_line((p1[0], p1[1], 0), (p2[0], p2[1], 0), dxfattribs={"layer": "COTAS"})
        mx = (p1[0] + p2[0]) / 2
        my = (p1[1] + p2[1]) / 2
        add_dxf_text(msp, label, mx, my, 0, text_height * 1.1, "COTAS")

    doc.saveas(path)


def export_kmz(path, result):
    points = result["points"]
    contours = result["contours"]
    feature_lines = result["feature_lines"]
    output_crs = result["output_crs"]
    kml = simplekml.Kml(name=result["project_name"])
    transformer = Transformer.from_crs(output_crs, CRS.from_epsg(4326), always_xy=True)

    styles = {}
    folders = {}
    for _, row in points.drop_duplicates("categoria").iterrows():
        category = row["categoria"]
        style = simplekml.Style()
        r, g, b = hex_to_rgb(row["color"])
        style.iconstyle.color = simplekml.Color.rgb(r, g, b, 255)
        style.iconstyle.scale = 0.9
        style.iconstyle.icon.href = row["icon"]
        style.labelstyle.scale = 0.65
        styles[category] = style
        folders[category] = kml.newfolder(name=category)

    for _, row in points.iterrows():
        lon, lat = transformer.transform(float(row["x"]), float(row["y"]))
        alt = 0 if pd.isna(row["z"]) else float(row["z"])
        folder = folders.get(row["categoria"], kml)
        pnt = folder.newpoint(name=str(row["punto"]), coords=[(lon, lat, alt)])
        pnt.description = f"Archivo: {row['source_file']}<br>Descripcion: {row['descripcion']}<br>Cota: {format_z(row['z'])}<br>Categoria: {row['categoria']}"
        pnt.style = styles.get(row["categoria"])

    if contours:
        contour_folder = kml.newfolder(name="Curvas de nivel")
        contour_style = simplekml.Style()
        contour_style.linestyle.color = simplekml.Color.rgb(109, 76, 65, 255)
        contour_style.linestyle.width = 1.4
        for contour in contours:
            coords = []
            for x, y in contour["coords"]:
                lon, lat = transformer.transform(float(x), float(y))
                coords.append((lon, lat, float(contour["level"])))
            line = contour_folder.newlinestring(name=f"Cota {contour['level']:.2f}", coords=coords)
            line.altitudemode = simplekml.AltitudeMode.clamptoground
            line.style = contour_style

    if feature_lines:
        line_folder = kml.newfolder(name="Polilineas detectadas")
        styles_by_cat = {}
        for feature in feature_lines:
            if feature["category"] not in styles_by_cat:
                style = simplekml.Style()
                r, g, b = hex_to_rgb(feature["color"])
                style.linestyle.color = simplekml.Color.rgb(r, g, b, 255)
                style.linestyle.width = 2.5 if feature["category"] == "TRAZA_PK" else 1.8
                styles_by_cat[feature["category"]] = style
            coords = []
            raw_coords = feature["coords"] + ([feature["coords"][0]] if feature.get("closed") and len(feature["coords"]) >= 3 else [])
            for x, y, z in raw_coords:
                lon, lat = transformer.transform(float(x), float(y))
                coords.append((lon, lat, 0 if z is None else float(z)))
            line = line_folder.newlinestring(name=feature["name"], coords=coords)
            line.altitudemode = simplekml.AltitudeMode.clamptoground
            line.style = styles_by_cat[feature["category"]]

    kml.savekmz(path)


def export_excel(path, result):
    points = result["points"]
    qc = result["qc"]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        points.to_excel(writer, sheet_name="Puntos procesados", index=False)
        qc.to_excel(writer, sheet_name="Control calidad", index=False)
        points["categoria"].value_counts().rename_axis("categoria").reset_index(name="cantidad").to_excel(writer, sheet_name="Categorias", index=False)


def export_folium_map(path, result):
    points = result["points"]
    contours = result["contours"]
    feature_lines = result["feature_lines"]
    output_crs = result["output_crs"]
    transformer = Transformer.from_crs(output_crs, CRS.from_epsg(4326), always_xy=True)
    lon, lat = transformer.transform(points["x"].mean(), points["y"].mean())
    fmap = folium.Map(location=[lat, lon], zoom_start=17, control_scale=True, tiles="OpenStreetMap")
    folium.TileLayer("CartoDB positron", name="Plano claro").add_to(fmap)

    for category, group in points.groupby("categoria"):
        fg = folium.FeatureGroup(name=category, show=True)
        for _, row in group.iterrows():
            lon, lat = transformer.transform(float(row["x"]), float(row["y"]))
            popup = f"<b>{row['punto']}</b><br>Archivo: {row['source_file']}<br>{row['descripcion']}<br>Cota: {format_z(row['z'])}"
            folium.CircleMarker(location=[lat, lon], radius=4, color=row["color"], fill=True, fill_color=row["color"], fill_opacity=0.85, popup=popup).add_to(fg)
        fg.add_to(fmap)

    if feature_lines:
        fg = folium.FeatureGroup(name="Polilineas detectadas", show=True)
        for feature in feature_lines:
            coords = []
            raw_coords = feature["coords"] + ([feature["coords"][0]] if feature.get("closed") and len(feature["coords"]) >= 3 else [])
            for x, y, z in raw_coords:
                lon, lat = transformer.transform(float(x), float(y))
                coords.append([lat, lon])
            folium.PolyLine(coords, color=feature["color"], weight=3 if feature["category"] == "TRAZA_PK" else 2, opacity=0.9, tooltip=feature["name"]).add_to(fg)
        fg.add_to(fmap)

    if contours:
        fg = folium.FeatureGroup(name="Curvas de nivel", show=True)
        for contour in contours:
            coords = []
            for x, y in contour["coords"]:
                lon, lat = transformer.transform(float(x), float(y))
                coords.append([lat, lon])
            folium.PolyLine(coords, color="#6d4c41", weight=1.6, opacity=0.85, tooltip=f"Cota {contour['level']:.2f}").add_to(fg)
        fg.add_to(fmap)

    folium.LayerControl().add_to(fmap)
    fmap.save(path)


def make_safe_name(text):
    text = str(text or "entrega_topografica").strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "_", text)
    return text.strip("_") or "entrega_topografica"


def make_output_path(project_name, suffix):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{make_safe_name(project_name)}_{stamp}"
    out_dir = OUTPUT_DIR / base
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{base}.{suffix}"


def prepare_project_result(file_items, file_configs, project_config, review_state):
    output_crs = parse_crs(project_config["output_crs"])
    all_points = []
    dropped_total = 0

    for file_item in file_items:
        cfg = file_configs[file_item["name"]]
        input_crs = parse_crs(cfg["input_crs"])
        pts, dropped = standardize_points(file_item, cfg, review_state)
        dropped_total += dropped
        if not pts.empty:
            pts = transform_points(pts, input_crs, output_crs)
            all_points.append(pts)

    if not all_points:
        raise ValueError("No quedaron puntos validos para procesar.")

    points = pd.concat(all_points, ignore_index=True)
    qc = quality_checks(points, dropped_total)
    contours, contour_message = create_contours(points, project_config["interval"], project_config["tn_pattern"])
    feature_lines = build_feature_lines(points)
    annotations = make_distance_annotations(points, output_crs)

    return {
        "project_name": project_config["project_name"],
        "points": points,
        "qc": qc,
        "contours": contours,
        "contour_message": contour_message,
        "feature_lines": feature_lines,
        "annotations": annotations,
        "output_crs": output_crs,
        "interval": project_config["interval"],
        "label_points": project_config["label_points"],
        "use_basemap": project_config["use_basemap"],
        "basemap_provider": project_config["basemap_provider"],
    }
"""


upload_md = r"""
## 3. Cargar archivos de puntos

Puedes seleccionar uno o varios archivos a la vez. La celda muestra una vista previa de cada archivo para que despues puedas confirmar columnas y formato.
"""


upload_code = r"""
if files is None:
    raise RuntimeError("Esta celda esta pensada para Google Colab.")

uploaded = files.upload()
if not uploaded:
    raise ValueError("No se subio ningun archivo.")

loaded_files = []
read_errors = []
for name in uploaded.keys():
    path = Path(name)
    try:
        df = read_points_file(path)
        loaded_files.append({"name": name, "path": path, "df": df})
    except Exception as exc:
        read_errors.append((name, str(exc)))

if read_errors:
    display(Markdown("### Archivos con error de lectura"))
    display(pd.DataFrame(read_errors, columns=["archivo", "error"]))

if not loaded_files:
    raise ValueError("No se pudo leer ningun archivo.")

summary = pd.DataFrame([
    {"archivo": item["name"], "filas": len(item["df"]), "columnas": len(item["df"].columns), "nombres_columnas": ", ".join(map(str, item["df"].columns[:8]))}
    for item in loaded_files
])
display(Markdown("### Archivos cargados"))
display(summary)

auto_detection_table = detection_summary(loaded_files)
display(Markdown("### Deteccion automatica inicial"))
display(auto_detection_table)

tabs = []
titles = []
for item in loaded_files:
    out = widgets.Output()
    with out:
        display(Markdown(f"**{item['name']}**"))
        display(item["df"].head(8))
    tabs.append(out)
    titles.append(item["name"][:28])
tab = widgets.Tab(children=tabs)
for i, title in enumerate(titles):
    tab.set_title(i, title)
display(tab)
"""


config_md = r"""
## 4. Configurar formato, CRS y salida

Primero indica si los archivos comparten formato y CRS. Si no, completa cada archivo en su panel.

Recuerda:

- `Este/Longitud` es la coordenada horizontal GIS.
- `Norte/Latitud` es la coordenada vertical GIS.
- Para Argentina, muchas libretas traen `X = Norte` y `Y = Este`; en ese caso activa `Intercambiar ejes`.
- Si el CRS de salida es distinto al de entrada, la herramienta transforma coordenadas.
"""


config_code = r"""
if "loaded_files" not in globals():
    raise RuntimeError("Primero carga archivos en la celda anterior.")

display(HTML('''
<style>
.topo-panel {
  border: 1px solid #d0d7de;
  border-radius: 8px;
  padding: 10px 12px;
  margin: 6px 0 12px 0;
  background: #fbfbfc;
}
.widget-label {
  font-weight: 600 !important;
}
.jupyter-widgets.widget-dropdown select,
.jupyter-widgets.widget-combobox input,
.jupyter-widgets.widget-text input {
  border-radius: 6px !important;
  border: 1px solid #b8c0cc !important;
}
</style>
'''))

wide = widgets.Layout(width="620px")
mid = widgets.Layout(width="420px")
style = {"description_width": "170px"}

auto_detections = {item["name"]: auto_detect_file_config(item) for item in loaded_files}
detected_crs_values = [det["input_crs"] for det in auto_detections.values() if det.get("input_crs")]
default_input_crs = detected_crs_values[0] if detected_crs_values else "EPSG:5344"
default_output_crs = default_input_crs if default_input_crs in [value for _, value in CRS_OPTIONS] else "CUSTOM"
same_detected_crs = len(set(detected_crs_values)) <= 1

display(Markdown("### Confirmacion rapida"))
display(Markdown("La herramienta ya intento detectar columnas, orden de ejes y CRS. Si algo no coincide, abre **Ajustes avanzados** y corrige solo ese punto."))
display(detection_summary(loaded_files))

project_w = widgets.Text(value="Entrega topografica", description="Nombre del plano", style=style, layout=wide)
auto_mode_w = widgets.Checkbox(value=True, description="Usar deteccion automatica")
same_format_w = widgets.Checkbox(value=True, description="Mismo formato de columnas para todos")
same_crs_w = widgets.Checkbox(value=same_detected_crs, description="Mismo CRS de entrada para todos")
output_crs_w = widgets.Dropdown(options=CRS_OPTIONS, value=default_output_crs, description="CRS salida", style=style, layout=wide)
output_custom_w = widgets.Text(value=default_input_crs if default_output_crs == "CUSTOM" else "", description="CRS salida custom", placeholder="Ej: EPSG:5347", style=style, layout=wide)
interval_w = widgets.FloatText(value=0.50, description="Equidistancia", style=style, layout=mid)
tn_pattern_w = widgets.Text(value=r"\bTN\b", description="Patron TN", style=style, layout=mid)
label_points_w = widgets.Checkbox(value=True, description="Etiquetar puntos en PDF/DXF")
use_basemap_w = widgets.Checkbox(value=True, description="Usar mapa de fondo en PDF")
basemap_provider_w = widgets.Dropdown(options=["OpenStreetMap", "CartoDB Positron", "CartoDB Voyager"], value="OpenStreetMap", description="Mapa base", style=style, layout=wide)


def make_file_widget_set(item, title):
    df = item["df"]
    det = auto_detections[item["name"]] if item["name"] in auto_detections else auto_detect_file_config(item)
    col_options = [None] + list(df.columns)
    box_title = widgets.HTML(f"<div class='topo-panel'><b>{title}</b><br><span style='color:#57606a'>Filas: {len(df)} | Columnas: {len(df.columns)}</span></div>")
    organization_w = widgets.Dropdown(
        options=[
            ("Punto, Este, Norte, Cota, Descripcion", "standard"),
            ("Punto, Norte, Este, Cota, Descripcion", "northing_first"),
            ("Longitud, Latitud, Cota, Descripcion", "lonlat"),
            ("Latitud, Longitud, Cota, Descripcion", "latlon"),
            ("Personalizado", "custom"),
        ],
        value=det.get("organization", "standard") if det.get("organization", "custom") in ["standard", "northing_first", "lonlat", "latlon", "custom"] else "standard",
        description="Organizacion",
        style=style,
        layout=wide,
    )
    input_value = det.get("input_crs", default_input_crs)
    input_dropdown_value = input_value if input_value in [value for _, value in CRS_OPTIONS] else "CUSTOM"
    input_crs_w = widgets.Dropdown(options=CRS_OPTIONS, value=input_dropdown_value, description="CRS entrada", style=style, layout=wide)
    input_custom_w = widgets.Text(value=input_value if input_dropdown_value == "CUSTOM" else "", description="CRS entrada custom", placeholder="Ej: EPSG:32721", style=style, layout=wide)
    point_w = widgets.Dropdown(options=col_options, value=det.get("point_col"), description="Punto / ID", style=style, layout=wide)
    x_w = widgets.Dropdown(options=col_options, value=det.get("x_col"), description="Este / Lon", style=style, layout=wide)
    y_w = widgets.Dropdown(options=col_options, value=det.get("y_col"), description="Norte / Lat", style=style, layout=wide)
    z_w = widgets.Dropdown(options=col_options, value=det.get("z_col"), description="Z / Cota", style=style, layout=wide)
    desc_w = widgets.Dropdown(options=col_options, value=det.get("desc_col"), description="Descripcion", style=style, layout=wide)
    swap_xy_w = widgets.Checkbox(value=bool(det.get("swap_xy", False)), description="Intercambiar ejes al procesar")

    def on_org_change(change):
        if change["new"] in {"northing_first", "latlon"}:
            swap_xy_w.value = True
        elif change["new"] in {"standard", "lonlat"}:
            swap_xy_w.value = False

    organization_w.observe(on_org_change, names="value")

    panel = widgets.VBox([
        box_title,
        organization_w,
        input_crs_w,
        input_custom_w,
        widgets.HTML("<b>Columnas</b>"),
        point_w,
        x_w,
        y_w,
        z_w,
        desc_w,
        swap_xy_w,
    ])
    return {
        "panel": panel,
        "df": df,
        "organization_w": organization_w,
        "input_crs_w": input_crs_w,
        "input_custom_w": input_custom_w,
        "point_w": point_w,
        "x_w": x_w,
        "y_w": y_w,
        "z_w": z_w,
        "desc_w": desc_w,
        "swap_xy_w": swap_xy_w,
    }


common_widgets = make_file_widget_set(loaded_files[0], "Formato comun para todos los archivos")
per_file_widgets = {item["name"]: make_file_widget_set(item, item["name"]) for item in loaded_files}

accordion = widgets.Accordion(children=[common_widgets["panel"]] + [per_file_widgets[item["name"]]["panel"] for item in loaded_files])
accordion.set_title(0, "Formato comun")
for i, item in enumerate(loaded_files, start=1):
    accordion.set_title(i, item["name"][:40])
accordion.selected_index = None

display(widgets.VBox([
    widgets.HTML("<h3>Proyecto y salida</h3>"),
    project_w,
    auto_mode_w,
    same_format_w,
    same_crs_w,
    output_crs_w,
    output_custom_w,
    widgets.HTML("<h3>Curvas y plano</h3>"),
    widgets.HBox([interval_w, tn_pattern_w]),
    label_points_w,
    use_basemap_w,
    basemap_provider_w,
    widgets.HTML("<h3>Ajustes avanzados de archivos</h3>"),
    accordion,
]))


def widget_set_to_config(wset):
    return {
        "organization": wset["organization_w"].value,
        "input_crs": selected_crs_value(wset["input_crs_w"].value, wset["input_custom_w"].value),
        "point_col": wset["point_w"].value,
        "x_col": wset["x_w"].value,
        "y_col": wset["y_w"].value,
        "z_col": wset["z_w"].value,
        "desc_col": wset["desc_w"].value,
        "swap_xy": bool(wset["swap_xy_w"].value),
    }


def collect_file_configs():
    configs = {}
    base_item = loaded_files[0]
    common_cfg = widget_set_to_config(common_widgets)
    for item in loaded_files:
        if auto_mode_w.value:
            det = auto_detections[item["name"]]
            cfg = {
                "organization": det["organization"],
                "input_crs": default_input_crs if same_crs_w.value else det["input_crs"],
                "point_col": det["point_col"],
                "x_col": det["x_col"],
                "y_col": det["y_col"],
                "z_col": det["z_col"],
                "desc_col": det["desc_col"],
                "swap_xy": bool(det.get("swap_xy", False)),
            }
        elif same_format_w.value:
            cfg = dict(common_cfg)
            cfg["point_col"] = resolve_col_by_position(base_item["df"], item["df"], common_cfg["point_col"])
            cfg["x_col"] = resolve_col_by_position(base_item["df"], item["df"], common_cfg["x_col"])
            cfg["y_col"] = resolve_col_by_position(base_item["df"], item["df"], common_cfg["y_col"])
            cfg["z_col"] = resolve_col_by_position(base_item["df"], item["df"], common_cfg["z_col"])
            cfg["desc_col"] = resolve_col_by_position(base_item["df"], item["df"], common_cfg["desc_col"])
        else:
            cfg = widget_set_to_config(per_file_widgets[item["name"]])

        if not same_crs_w.value:
            own_cfg = widget_set_to_config(per_file_widgets[item["name"]])
            cfg["input_crs"] = own_cfg["input_crs"]
        configs[item["name"]] = cfg
    return configs


def collect_project_config():
    return {
        "project_name": project_w.value.strip() or "Entrega topografica",
        "output_crs": selected_crs_value(output_crs_w.value, output_custom_w.value),
        "interval": float(interval_w.value),
        "tn_pattern": tn_pattern_w.value,
        "label_points": bool(label_points_w.value),
        "use_basemap": bool(use_basemap_w.value),
        "basemap_provider": basemap_provider_w.value,
    }
"""


review_md = r"""
## 5. Revisar errores antes de exportar

Ejecuta la revision. Si aparece un punto con error, puedes editarlo o saltarlo. Los avisos no bloquean la exportacion, pero conviene mirarlos.
"""


review_code = r"""
if "loaded_files" not in globals() or "collect_file_configs" not in globals():
    raise RuntimeError("Primero carga archivos y configura columnas.")

review_state = {"skipped": {}, "edits": {}}
review_output = widgets.Output()
editor_output = widgets.Output()

file_select_w = widgets.Dropdown(description="Archivo", style={"description_width": "90px"}, layout=widgets.Layout(width="520px"))
row_select_w = widgets.Dropdown(description="Fila", style={"description_width": "90px"}, layout=widgets.Layout(width="520px"))
punto_edit_w = widgets.Text(description="Punto/ID", style={"description_width": "90px"}, layout=widgets.Layout(width="520px"))
x_edit_w = widgets.Text(description="Este/Lon", style={"description_width": "90px"}, layout=widgets.Layout(width="520px"))
y_edit_w = widgets.Text(description="Norte/Lat", style={"description_width": "90px"}, layout=widgets.Layout(width="520px"))
z_edit_w = widgets.Text(description="Z/Cota", style={"description_width": "90px"}, layout=widgets.Layout(width="520px"))
desc_edit_w = widgets.Text(description="Desc.", style={"description_width": "90px"}, layout=widgets.Layout(width="520px"))

refresh_btn = widgets.Button(description="Revisar errores", icon="search", button_style="info")
save_btn = widgets.Button(description="Guardar edicion", icon="check", button_style="success")
skip_btn = widgets.Button(description="Saltar punto", icon="trash", button_style="warning")

current_errors_df = pd.DataFrame()


def collect_validation_errors():
    file_configs = collect_file_configs()
    frames = []
    for item in loaded_files:
        frame = validate_configured_file(item, file_configs[item["name"]], review_state)
        if not frame.empty:
            frames.append(frame)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame(columns=["archivo", "fila", "severidad", "campo", "problema", "valor"])


def unique_error_rows(errors_df):
    if errors_df.empty:
        return []
    rows = errors_df[errors_df["severidad"] == "ERROR"][["archivo", "fila"]].drop_duplicates()
    rows = rows[rows["fila"] > 0]
    return [(f"{r.archivo} | fila {int(r.fila)}", (r.archivo, int(r.fila))) for r in rows.itertuples(index=False)]


def get_file_item(name):
    return next(item for item in loaded_files if item["name"] == name)


def populate_editor(*args):
    editor_output.clear_output()
    if not row_select_w.value:
        return
    file_name, row_no = row_select_w.value
    item = get_file_item(file_name)
    cfg = collect_file_configs()[file_name]
    row = item["df"].iloc[row_no - 1]
    edits = review_state.get("edits", {}).get(file_name, {}).get(row_no, {})

    punto_edit_w.value = str(edits.get("punto", get_cell(row, cfg.get("point_col"))))
    x_edit_w.value = str(edits.get("x", get_cell(row, cfg.get("x_col"))))
    y_edit_w.value = str(edits.get("y", get_cell(row, cfg.get("y_col"))))
    z_edit_w.value = str(edits.get("z", get_cell(row, cfg.get("z_col"))))
    desc_edit_w.value = str(edits.get("descripcion", get_cell(row, cfg.get("desc_col"))))

    with editor_output:
        problems = current_errors_df[(current_errors_df["archivo"] == file_name) & (current_errors_df["fila"] == row_no)]
        display(Markdown("**Problemas detectados para esta fila:**"))
        display(problems[["severidad", "campo", "problema", "valor"]])


def refresh_review(_=None):
    global current_errors_df
    current_errors_df = collect_validation_errors()
    with review_output:
        clear_output()
        if current_errors_df.empty:
            display(Markdown("**Sin errores ni avisos detectados.**"))
        else:
            display(Markdown("### Errores y avisos detectados"))
            display(current_errors_df)
            error_count = int((current_errors_df["severidad"] == "ERROR").sum())
            if error_count:
                display(Markdown(f"**Quedan {error_count} errores. Edita o salta esos puntos antes de exportar.**"))
            else:
                display(Markdown("**No quedan errores bloqueantes.**"))

    options = unique_error_rows(current_errors_df)
    row_select_w.options = options
    if options:
        row_select_w.value = options[0][1]
        file_select_w.options = sorted(current_errors_df["archivo"].unique().tolist())
        file_select_w.value = row_select_w.value[0]
        populate_editor()
    else:
        row_select_w.options = []
        file_select_w.options = []
        editor_output.clear_output()


def save_edit(_):
    if not row_select_w.value:
        return
    file_name, row_no = row_select_w.value
    review_state.setdefault("edits", {}).setdefault(file_name, {})[int(row_no)] = {
        "punto": punto_edit_w.value,
        "x": x_edit_w.value,
        "y": y_edit_w.value,
        "z": z_edit_w.value,
        "descripcion": desc_edit_w.value,
    }
    refresh_review()


def skip_point(_):
    if not row_select_w.value:
        return
    file_name, row_no = row_select_w.value
    review_state.setdefault("skipped", {}).setdefault(file_name, set()).add(int(row_no))
    refresh_review()


refresh_btn.on_click(refresh_review)
save_btn.on_click(save_edit)
skip_btn.on_click(skip_point)
row_select_w.observe(populate_editor, names="value")

display(widgets.VBox([
    widgets.HBox([refresh_btn]),
    review_output,
    widgets.HTML("<h3>Editar o saltar punto con error</h3>"),
    row_select_w,
    punto_edit_w,
    x_edit_w,
    y_edit_w,
    z_edit_w,
    desc_edit_w,
    widgets.HBox([save_btn, skip_btn]),
    editor_output,
]))

refresh_review()
"""


export_md = r"""
## 6. Exportar entregables con botones independientes

No se genera ZIP. Cada boton procesa los datos actuales, crea ese entregable y lo descarga.
"""


export_code = r"""
if "loaded_files" not in globals() or "collect_file_configs" not in globals():
    raise RuntimeError("Primero configura y revisa los archivos.")

export_output = widgets.Output()
preview_output = widgets.Output()

prepare_btn = widgets.Button(description="Preparar / vista previa", icon="refresh", button_style="info", layout=widgets.Layout(width="210px"))
pdf_btn = widgets.Button(description="PDF", icon="file-pdf-o", button_style="danger", layout=widgets.Layout(width="120px"))
dxf_btn = widgets.Button(description="DXF", icon="cube", button_style="primary", layout=widgets.Layout(width="120px"))
kmz_btn = widgets.Button(description="KMZ", icon="globe", button_style="primary", layout=widgets.Layout(width="120px"))
xlsx_btn = widgets.Button(description="XLSX", icon="table", button_style="success", layout=widgets.Layout(width="120px"))
html_btn = widgets.Button(description="HTML", icon="map", button_style="success", layout=widgets.Layout(width="120px"))

current_result = None


def unresolved_error_count():
    if "collect_validation_errors" in globals():
        errors_df = collect_validation_errors()
    else:
        file_configs = collect_file_configs()
        frames = []
        state = review_state if "review_state" in globals() else {"skipped": {}, "edits": {}}
        for item in loaded_files:
            frame = validate_configured_file(item, file_configs[item["name"]], state)
            if not frame.empty:
                frames.append(frame)
        errors_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if errors_df.empty:
        return 0
    return int((errors_df["severidad"] == "ERROR").sum())


def prepare_current_result(force=True):
    global current_result
    error_count = unresolved_error_count()
    if error_count:
        raise ValueError(f"Quedan {error_count} errores sin resolver. Edita o salta esos puntos en la seccion de revision.")
    file_configs = collect_file_configs()
    project_config = collect_project_config()
    current_result = prepare_project_result(loaded_files, file_configs, project_config, review_state if "review_state" in globals() else {"skipped": {}, "edits": {}})
    return current_result


def show_preview(result):
    with preview_output:
        clear_output()
        display(Markdown("### Vista previa procesada"))
        display(Markdown(result["contour_message"]))
        display(Markdown(f"**Polilineas detectadas:** {len(result['feature_lines'])}"))
        display(result["qc"])
        display(result["points"][["source_file", "source_row", "punto", "x", "y", "z", "descripcion", "categoria"]].head(20))


def on_prepare(_):
    with export_output:
        clear_output()
        try:
            result = prepare_current_result()
            show_preview(result)
            display(Markdown("**Datos preparados. Ya puedes exportar con los botones.**"))
        except Exception as exc:
            display(Markdown(f"**No se pudo preparar:** {exc}"))


def download_file(path):
    display(Markdown(f"Archivo generado: `{path}`"))
    if files is not None:
        files.download(str(path))


def export_one(kind):
    with export_output:
        clear_output()
        try:
            result = prepare_current_result()
            suffix = {"pdf": "pdf", "dxf": "dxf", "kmz": "kmz", "xlsx": "xlsx", "html": "html"}[kind]
            path = make_output_path(result["project_name"], suffix)
            if kind == "pdf":
                build_pdf_report(path, result)
            elif kind == "dxf":
                export_dxf(path, result)
            elif kind == "kmz":
                export_kmz(path, result)
            elif kind == "xlsx":
                export_excel(path, result)
            elif kind == "html":
                export_folium_map(path, result)
                display(HTML(Path(path).read_text(encoding="utf-8")))
            show_preview(result)
            download_file(path)
        except Exception as exc:
            display(Markdown(f"**No se pudo exportar {kind.upper()}:** {exc}"))


prepare_btn.on_click(on_prepare)
pdf_btn.on_click(lambda _: export_one("pdf"))
dxf_btn.on_click(lambda _: export_one("dxf"))
kmz_btn.on_click(lambda _: export_one("kmz"))
xlsx_btn.on_click(lambda _: export_one("xlsx"))
html_btn.on_click(lambda _: export_one("html"))

display(widgets.VBox([
    widgets.HBox([prepare_btn, pdf_btn, dxf_btn, kmz_btn, xlsx_btn, html_btn]),
    export_output,
    preview_output,
]))
"""


tips_md = r"""
## 7. Criterios de uso

- Para curvas de nivel, los puntos de terreno deben contener `TN` en la descripcion.
- Para planos y distancias, conviene usar un CRS de salida proyectado en metros.
- Si los puntos caen desplazados, revisa CRS, zona POSGAR/UTM y orden de ejes.
- El mapa de fondo depende de internet en Colab y es referencial.
- Las acotaciones automaticas son de apoyo: ancho, alto y mayor diagonal del conjunto.
"""


def md_cell(text):
    return {"cell_type": "markdown", "metadata": {}, "source": src(text)}


def code_cell(text):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": src(text)}


nb = {
    "cells": [
        md_cell(intro_md),
        md_cell(install_md),
        code_cell(install_code),
        md_cell(helpers_md),
        code_cell(helpers_code),
        md_cell(upload_md),
        code_cell(upload_code),
        md_cell(config_md),
        code_cell(config_code),
        md_cell(review_md),
        code_cell(review_code),
        md_cell(export_md),
        code_cell(export_code),
        md_cell(tips_md),
    ],
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.x"},
        "colab": {"provenance": [], "collapsed_sections": []},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}


TARGET_NB.write_text(json.dumps(nb, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Notebook generado: {TARGET_NB.resolve()}")
