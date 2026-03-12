# Análisis Predictivo de Cobertura LTE: 800 MHz vs 1800 MHz

Comparativa de cobertura LTE en entorno residencial, combinando:
- modelo de propagación COST-231/Okumura-Hata,
- extracción geoespacial real desde OpenStreetMap (OSMnx),
- mapas de calor con umbral de servicio en **RSRP > -105 dBm**.

## Qué hace el script

Al ejecutar `python cobertura_lte.py`:
1. Descarga un barrio real (`Mirasierra, Madrid, Spain`) con su red viaria y edificios desde OSM.
2. Define un eNodeB virtual en coordenadas lat/lon configurables.
3. Calcula automáticamente un **segundo eNodeB en el extremo opuesto del barrio**.
4. Calcula Path Loss y RSRP para **800 MHz** y **1800 MHz** sobre puntos de calle.
5. Evalúa mejora de huella total con 2 sitios frente a 1 sitio.
6. Detecta zonas de **solape** (útiles para handover y sensibles a interferencia co-canal si el PCI no se planifica bien).
7. Emite un informe con recomendación de despliegue (cobertura vs capacidad).

## Modelos implementados

- **Okumura-Hata urbano** para 800 MHz (rango 150–1500 MHz).
- **COST-231 Hata** para 1800 MHz (rango 1500–2000 MHz).

RSRP calculado mediante link budget:

`RSRP = EIRP - PathLoss + G_UE - márgenes - pérdidas de penetración`

## Dependencias

Instalación:

```bash
pip install -r requirements.txt
```

Incluye stack geoespacial (`osmnx`, `geopandas`, `shapely`).

Incluye backend/API (`Flask`, `flask-cors`) para simulación interactiva web.

## Modo Web Interactivo (Leaflet + Flask)

### 1) Arranque

```bash
python app.py
```

Abrir en navegador:

`http://localhost:5000`

### 2) Frontend

- Visor con Leaflet sobre mapa base OpenStreetMap.
- Clic en mapa para capturar latitud y longitud del eNodeB.
- Formulario para seleccionar frecuencia (`800` / `1800` MHz) y radio de análisis.
- Botón **Ejecutar Simulación**.

### 3) API backend

- Endpoint: `POST /api/simulate`
- Endpoint health: `GET /api/health`
- CORS habilitado para rutas `/api/*`.

Ejemplo de payload:

```json
{
	"lat": 40.4916,
	"lon": -3.7212,
	"frecuencia_mhz": 800,
	"radio_m": 500,
	"umbral_dbm": -105,
	"muestreo_m": 30
}
```

### 4) Motor de cálculo dinámico

- OSMnx descarga dinámicamente la red viaria en un radio alrededor de la coordenada.
- Se muestrean puntos sobre calles y se calcula distancia real al eNodeB.
- Se calcula RSRP (COST-231/Okumura-Hata según frecuencia) por punto.
- El backend devuelve GeoJSON con atributos de cobertura.

### 5) Visualización de resultados

- El frontend renderiza la capa georreferenciada sobre Leaflet.
- Colores:
	- Verde: `RSRP > -105 dBm`
	- Rojo: `RSRP <= -105 dBm`

## Salidas en `resultados/`

- `figura1_perdida_trayecto.png`
- `figura2_rsrp_vs_distancia.png`
- `figura3_radios_cobertura.png`
- `figura4_mapa_cobertura_2d.png`
- `figura5_diferencia_cobertura.png`
- `figura6_perdida_vs_frecuencia.png`
- `figura7_heatmap_geoespacial.png`
- `figura8_delta_geoespacial.png`
- `figura9_solape_dual_enodeb.png`
- `tabla_cobertura.csv`
- `tabla_cobertura_geoespacial.csv`

## Criterio operativo en mapas

- **Cobertura válida**: `RSRP > -105 dBm`
- **Zona ciega**: `RSRP < -105 dBm`

En los heatmaps, el colormap está centrado en `-105 dBm` para separar visualmente ambas zonas.

## Evaluación de 2 eNodeB

El informe geoespacial incluye automáticamente:
- Cobertura con 1 eNodeB vs cobertura combinada con 2 eNodeB (incremento en puntos porcentuales).
- Zonas de solape por banda (800/1800 MHz).
- Subconjunto de solape balanceado `|ΔRSRP| ≤ 3 dB`, donde son más probables handovers frecuentes.

Interpretación de solape:
- Solape útil: mejora continuidad de servicio y robustez de movilidad.
- Solape excesivo sin planificación PCI/tilt/potencia: aumenta riesgo de interferencia co-canal y handovers no óptimos.

## Conclusión técnica esperada (fase inicial)

- **800 MHz**: preferible como capa inicial de cobertura por mayor alcance y mejor penetración.
- **1800 MHz**: preferible como capa de capacidad en zonas densas y con más tráfico.

Estrategia recomendada de despliegue:
1. Encender primero 800 MHz para continuidad de servicio residencial/indoor.
2. Densificar con 1800 MHz para absorber crecimiento de tráfico.

## Tests

```bash
python -m pytest tests/ -v
```