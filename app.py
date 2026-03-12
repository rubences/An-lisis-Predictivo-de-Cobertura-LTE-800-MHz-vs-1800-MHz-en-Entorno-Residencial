import os
from typing import Any

import geopandas as gpd
import osmnx as ox
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from cobertura_lte import LINK_BUDGET, SCENARIO, rsrp_dbm


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


def _validate_payload(payload: dict[str, Any]) -> tuple[float, float, int, int, float, float]:
    lat = float(payload.get("lat"))
    lon = float(payload.get("lon"))
    frecuencia_mhz = int(payload.get("frecuencia_mhz", 800))
    radio_m = int(payload.get("radio_m", 500))
    umbral_dbm = float(payload.get("umbral_dbm", -105))
    muestreo_m = float(payload.get("muestreo_m", 30))

    if frecuencia_mhz not in (800, 1800):
        raise ValueError("frecuencia_mhz debe ser 800 o 1800")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Coordenadas inválidas")
    if radio_m < 100 or radio_m > 3000:
        raise ValueError("radio_m debe estar entre 100 y 3000")
    if muestreo_m <= 5 or muestreo_m > 100:
        raise ValueError("muestreo_m debe estar entre 5 y 100")

    return lat, lon, frecuencia_mhz, radio_m, umbral_dbm, muestreo_m


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
        lat, lon, frecuencia_mhz, radio_m, umbral_dbm, muestreo_m = _validate_payload(payload)

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
        points["rsrp_dbm"] = points["distancia_km"].apply(
            lambda d: rsrp_dbm(
                frecuencia_mhz,
                d,
                SCENARIO,
                LINK_BUDGET,
                incluir_penetracion=True,
                entorno="urbano",
            )
        )
        points["covered"] = points["rsrp_dbm"] > umbral_dbm

        points_wgs84 = points.to_crs("EPSG:4326")
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
                        "distancia_km": round(float(row["distancia_km"]), 3),
                    },
                }
            )

        total = int(len(points_wgs84))
        covered_count = int(points_wgs84["covered"].sum())
        uncovered_count = total - covered_count

        return jsonify(
            {
                "input": {
                    "lat": lat,
                    "lon": lon,
                    "frecuencia_mhz": frecuencia_mhz,
                    "radio_m": radio_m,
                    "umbral_dbm": umbral_dbm,
                    "muestreo_m": muestreo_m,
                },
                "summary": {
                    "total_points": total,
                    "covered_points": covered_count,
                    "uncovered_points": uncovered_count,
                    "coverage_pct": round((covered_count / total) * 100, 2) if total else 0.0,
                },
                "geojson": feature_collection,
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Error en simulación: {exc}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)