import os
from typing import Any

import base64
import io
import numpy as np
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import osmnx as ox
from shapely.geometry import Point
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from cobertura_lte import LINK_BUDGET, SCENARIO, rsrp_dbm, rsrp_dbm_with_los


app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/api/*": {"origins": "*"}})


def _sample_points_on_edges(edges: gpd.GeoDataFrame, step_m: float) -> gpd.GeoDataFrame:
    points = []
    for geom in edges.geometry:
        if geom is None or geom.is_empty:
            continue
        length = geom.length
        if length <= 0:
            continue
        count = max(1, int(length // step_m))
        for index in range(count + 1):
            distance = min(length, index * step_m)
            points.append(geom.interpolate(distance))

    if not points:
        return gpd.GeoDataFrame(geometry=[], crs=edges.crs)
    return gpd.GeoDataFrame(geometry=points, crs=edges.crs)


def _download_buildings(lat: float, lon: float, radio_m: int) -> gpd.GeoDataFrame | None:
    """Descarga polígonos de edificios con OSMnx en radio alrededor del punto."""
    try:
        buildings = ox.features_from_point(
            (lat, lon),
            dist=radio_m,
            tags={"building": True},
        )
        
        if buildings.empty:
            return None
        
        buildings = buildings[buildings.geometry.type.isin(["Polygon", "MultiPolygon"])]
        buildings_proj = ox.project_gdf(buildings)
        return buildings_proj if not buildings_proj.empty else None
    except Exception:
        return None


def _apply_indoor_penalty(point_geom: Point, rsrp_dbm: float, buildings: gpd.GeoDataFrame | None) -> tuple[float, bool]:
    """Si el punto está dentro de un edificio, aplica penalización extra de penetración."""
    if buildings is None or buildings.empty:
        return rsrp_dbm, False
    
    is_indoor = False
    for _, building in buildings.iterrows():
        if building.geometry.contains(point_geom):
            is_indoor = True
            rsrp_dbm -= 10.0
            break
    
    return rsrp_dbm, is_indoor


def _generate_raster(
    points: gpd.GeoDataFrame,
    umbral_dbm: float,
    bounds,
) -> str:
    """Genera un raster PNG (heatmap) en base64."""
    fig, ax = plt.subplots(figsize=(10, 10), dpi=80)
    
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "coverage",
        ["#8b0000", "#d73027", "#ffd166", "#1a9850"],
        N=256,
    )
    
    norm = mcolors.TwoSlopeNorm(vmin=-120, vcenter=umbral_dbm, vmax=-70)
    
    scatter = ax.scatter(
        points.geometry.x,
        points.geometry.y,
        c=points["rsrp_dbm"],
        cmap=cmap,
        norm=norm,
        s=50,
        alpha=0.8,
        edgecolors="none",
    )
    
    minx, miny, maxx, maxy = bounds
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.set_xlabel("Este (m)")
    ax.set_ylabel("Norte (m)")
    ax.set_title("Heatmap de Cobertura LTE")
    
    cbar = plt.colorbar(scatter, ax=ax, label="RSRP (dBm)")
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=80)
    buf.seek(0)
    plt.close(fig)
    
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def _validate_payload(payload: dict[str, Any]) -> tuple:
    lat = float(payload.get("lat"))
    lon = float(payload.get("lon"))
    lat2 = payload.get("lat2")
    lon2 = payload.get("lon2")
    
    if lat2 is not None:
        lat2 = float(lat2)
    if lon2 is not None:
        lon2 = float(lon2)
    
    frecuencia_mhz = int(payload.get("frecuencia_mhz", 800))
    radio_m = int(payload.get("radio_m", 500))
    umbral_dbm = float(payload.get("umbral_dbm", -105))
    muestreo_m = float(payload.get("muestreo_m", 30))
    output_mode = payload.get("output_mode", "points")
    enable_los = payload.get("enable_los", True)
    atenuacion_muro_db = float(payload.get("atenuacion_muro_db", 3.0))

    if frecuencia_mhz not in (800, 1800):
        raise ValueError("frecuencia_mhz debe ser 800 o 1800")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Coordenadas inválidas para lat/lon")
    if lat2 is not None and lon2 is not None:
        if not (-90 <= lat2 <= 90 and -180 <= lon2 <= 180):
            raise ValueError("Coordenadas inválidas para lat2/lon2")
    if radio_m < 100 or radio_m > 3000:
        raise ValueError("radio_m debe estar entre 100 y 3000")
    if muestreo_m <= 5 or muestreo_m > 100:
        raise ValueError("muestreo_m debe estar entre 5 y 100")
    if output_mode not in ("points", "raster"):
        raise ValueError("output_mode debe ser 'points' o 'raster'")
    if atenuacion_muro_db < 0 or atenuacion_muro_db > 10:
        raise ValueError("atenuacion_muro_db debe estar entre 0 y 10 dB")

    return lat, lon, lat2, lon2, frecuencia_mhz, radio_m, umbral_dbm, muestreo_m, output_mode, enable_los, atenuacion_muro_db


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/simulate")
def simulate():
    try:
        payload = request.get_json(force=True)
        lat, lon, lat2, lon2, frecuencia_mhz, radio_m, umbral_dbm, muestreo_m, output_mode, enable_los, atenuacion_muro_db = _validate_payload(payload)

        buildings = _download_buildings(lat, lon, radio_m)
        
        graph = ox.graph_from_point((lat, lon), dist=radio_m, network_type="drive")
        graph_proj = ox.project_graph(graph)
        _, edges = ox.graph_to_gdfs(graph_proj)

        points = _sample_points_on_edges(edges, muestreo_m)
        if points.empty:
            return jsonify({"error": "No se generaron puntos en la red viaria."}), 422

        center_wgs84 = gpd.GeoSeries.from_xy([lon], [lat], crs="EPSG:4326")
        center_proj = center_wgs84.to_crs(points.crs).iloc[0]

        distances_km = points.geometry.distance(center_proj).clip(
            lower=SCENARIO["distancia_min_km"] * 1000
        ) / 1000.0

        points["distancia_km"] = distances_km
        
        if buildings is not None and not buildings.empty:
            buildings_proj = buildings.to_crs(points.crs)
        else:
            buildings_proj = None
        
        points["num_buildings_los"] = 0
        points["is_indoor"] = False
        points["rsrp_dbm"] = 0.0
        points["server"] = "1"
        
        for idx, point_row in points.iterrows():
            if enable_los and buildings_proj is not None:
                rsrp1, num_bld, is_interior = rsrp_dbm_with_los(
                    frecuencia_mhz,
                    float(point_row["distancia_km"]),
                    SCENARIO,
                    LINK_BUDGET,
                    center_proj,
                    point_row.geometry,
                    buildings_proj,
                    atenuacion_muro_db=atenuacion_muro_db,
                    incluir_penetracion=True,
                    entorno="urbano",
                )
                points.at[idx, "num_buildings_los"] = num_bld
                points.at[idx, "is_indoor"] = is_interior
                rsrp = rsrp1
            else:
                rsrp = rsrp_dbm(
                    frecuencia_mhz,
                    float(point_row["distancia_km"]),
                    SCENARIO,
                    LINK_BUDGET,
                    incluir_penetracion=True,
                    entorno="urbano",
                )
                points.at[idx, "is_indoor"] = False
            
            points.at[idx, "rsrp_dbm"] = rsrp
            
            if lat2 is not None and lon2 is not None:
                center2_wgs84 = gpd.GeoSeries.from_xy([lon2], [lat2], crs="EPSG:4326")
                center2_proj = center2_wgs84.to_crs(points.crs).iloc[0]
                distance2_km = center2_proj.distance(point_row.geometry) / 1000.0
                
                if enable_los and buildings_proj is not None:
                    rsrp2, _, _ = rsrp_dbm_with_los(
                        frecuencia_mhz,
                        distance2_km,
                        SCENARIO,
                        LINK_BUDGET,
                        center2_proj,
                        point_row.geometry,
                        buildings_proj,
                        atenuacion_muro_db=atenuacion_muro_db,
                        incluir_penetracion=True,
                        entorno="urbano",
                    )
                else:
                    rsrp2 = rsrp_dbm(
                        frecuencia_mhz,
                        distance2_km,
                        SCENARIO,
                        LINK_BUDGET,
                        incluir_penetracion=True,
                        entorno="urbano",
                    )
                
                if rsrp2 > rsrp:
                    points.at[idx, "rsrp_dbm"] = rsrp2
                    points.at[idx, "server"] = "2"
        
        points["covered"] = points["rsrp_dbm"] > umbral_dbm
        points_wgs84 = points.to_crs("EPSG:4326")
        
        if output_mode == "raster":
            points_proj = points.copy()
            raster_b64 = _generate_raster(
                points_proj,
                umbral_dbm,
                points_proj.total_bounds,
            )
            
            total = int(len(points_wgs84))
            covered_count = int(points_wgs84["covered"].sum())
            indoor_count = int(points_wgs84["is_indoor"].sum())
            
            return jsonify(
                {
                    "input": {
                        "lat": lat,
                        "lon": lon,
                        "lat2": lat2,
                        "lon2": lon2,
                        "frecuencia_mhz": frecuencia_mhz,
                        "radio_m": radio_m,
                        "umbral_dbm": umbral_dbm,
                        "muestreo_m": muestreo_m,
                        "output_mode": output_mode,
                        "enable_los": enable_los,
                        "atenuacion_muro_db": atenuacion_muro_db,
                    },
                    "summary": {
                        "total_points": total,
                        "covered_points": covered_count,
                        "indoor_points": indoor_count,
                        "uncovered_points": total - covered_count,
                        "coverage_pct": round((covered_count / total) * 100, 2) if total else 0.0,
                    },
                    "raster_b64": raster_b64,
                }
            )
        
        feature_collection = {
            "type": "FeatureCollection",
            "features": [],
        }

        for _, row in points_wgs84.iterrows():
            feature_collection["features"].append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [row.geometry.x, row.geometry.y],
                    },
                    "properties": {
                        "rsrp_dbm": round(float(row["rsrp_dbm"]), 2),
                        "covered": bool(row["covered"]),
                        "is_indoor": bool(row["is_indoor"]),
                        "num_buildings_los": int(row["num_buildings_los"]),
                        "server": str(row["server"]),
                        "distancia_km": round(float(row["distancia_km"]), 3),
                    },
                }
            )

        total = int(len(points_wgs84))
        covered_count = int(points_wgs84["covered"].sum())
        indoor_count = int(points_wgs84["is_indoor"].sum())
        uncovered_count = total - covered_count

        bounds = points_wgs84.total_bounds.tolist()

        return jsonify(
            {
                "input": {
                    "lat": lat,
                    "lon": lon,
                    "lat2": lat2,
                    "lon2": lon2,
                    "frecuencia_mhz": frecuencia_mhz,
                    "radio_m": radio_m,
                    "umbral_dbm": umbral_dbm,
                    "muestreo_m": muestreo_m,
                    "output_mode": output_mode,
                    "enable_los": enable_los,
                    "atenuacion_muro_db": atenuacion_muro_db,
                },
                "summary": {
                    "total_points": total,
                    "covered_points": covered_count,
                    "indoor_points": indoor_count,
                    "uncovered_points": uncovered_count,
                    "coverage_pct": round((covered_count / total) * 100, 2) if total else 0.0,
                },
                "geojson": {
                    "type": "FeatureCollection",
                    "bounds": bounds,
                    "features": feature_collection["features"],
                }
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Error en simulación: {exc}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)