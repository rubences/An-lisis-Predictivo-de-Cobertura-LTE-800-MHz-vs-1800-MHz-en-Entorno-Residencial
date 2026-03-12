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

**Ray-Tracing Simplificado (Line of Sight - LOS):**
- OSMnx descarga dinámicamente la red viaria y los **polígonos de edificios reales** de OpenStreetMap.
- Se muestrean puntos sobre calles en una malla de 30m (configurable).
- Para cada punto, se traza una línea imaginaria (LOS) desde la antena hasta el punto receptor.
- Se cuentan cuántos edificios **intersectan la línea LOS** (ray-tracing simplificado).
- Cada edificio atravesado añade una atenuación adicional (default **3 dB**, configurable) al path loss.
- Si el receptor está dentro de un edificio, se aplica penalización extra:
  - **15 dB** para 800 MHz
  - **20 dB** para 1800 MHz (mayor penetración en 1800)

**Fórmula actualizada de RSRP:**
$$RSRP = P_{tx} + G_{tx} - (PL_{Hata} + N \times L_{muro}) + G_{UE} - Márgenes - L_{interior}$$

Donde:
- $N$: número de edificios que la reintercepción la LOS
- $L_{muro}$: atenuación por edificio (ej. 3 dB)
- $L_{interior}$: atenuación extra si el punto está dentro de un edificio

**Dual eNodeB con Best-Server Selection:**
- Permite colocar **dos antenas simultáneamente** en el mismo escenario.
- Calcula RSRP para ambas antenas de forma independiente.
- El frontend muestra **el mejor servidor** (highest RSRP) en cada punto.
- Útil para evaluar:
  - Solapamiento y mejora de cobertura
  - Handover feasibility (zona de equilibrio)
  - Distribución de carga entre dos sitios

### 5) Visualización de resultados

**Modo Puntos (GeoJSON):**
- El frontend renderiza la capa georreferenciada sobre Leaflet.
- En modo **monocelda**: colores verde/rojo según RSRP > -105 dBm
- En modo **dual eNodeB**: colores azul (servidor 1) y naranja (servidor 2)
- Popups con RSRP, distancia, interior, número de edificios en LOS y servidor activo

**Modo Raster (PNG Heatmap):**
- Heatmap visual denso con gradiente de colores.
- Rojo profundo: RSRP < -120 dBm (sin servicio).
- Verde: RSRP > -70 dBm (excelente).
- Centrado en umbral -105 dBm para clara separación de zonas cubiertas/ciegas.

### 6) Parámetros de la API

POST `/api/simulate`:

```json
{
  "lat": 40.4916,
  "lon": -3.7212,
  "lat2": null,
  "lon2": null,
  "frecuencia_mhz": 800,
  "radio_m": 500,
  "umbral_dbm": -105,
  "muestreo_m": 30,
  "output_mode": "points",
  "enable_los": true,
  "atenuacion_muro_db": 3.0
}
```

**Parámetros:**
- `lat`, `lon`: Coordenadas del eNodeB 1
- `lat2`, `lon2`: Coordenadas del eNodeB 2 (opcional, null para monocelda)
- `enable_los`: Activa ray-tracing simplificado (conteo de edificios en LOS)
- `atenuacion_muro_db`: Atenuación por cada edificio atravesado (0-10 dB)

**Respuesta (Puntos):**

```json
{
  "input": {...},
  "summary": {
    "total_points": 617,
    "covered_points": 600,
    "indoor_points": 120,
    "uncovered_points": 17,
    "coverage_pct": 97.24
  },
  "geojson": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-3.72, 40.49]},
        "properties": {
          "rsrp_dbm": -95.2,
          "covered": true,
          "is_indoor": false,
          "num_buildings_los": 2,
          "server": "1",
          "distancia_km": 0.15
        }
      }
    ]
  }
}
```

**Respuesta (Raster):**

```json
{
  "input": {...},
  "summary": {...},
  "raster_b64": "data:image/png;base64,..."
}
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

### 7) Interfaz de Usuario (UI)

**Colocación de antenas:**
- **eNodeB 1**: Clic normal en el mapa para capturar la primera antena.
- **eNodeB 2** (Dual mode): Activa el checkbox "Dual eNodeB" y luego **Ctrl+clic** en el mapa para capturar la segunda antena.

**Opciones de Ray-Tracing:**
- **Activar ray-tracing + LOS**: Checkbox para habilitar conteo de edificios en la línea de vista.
  - Desactivado: usa solo path loss de Hata.
  - Activado: suma atenuación por cada edificio que la LOS atraviesa.
- **Atenuación por edificio (dB)**: Control deslizante para ajustar cuántos dB resta cada edificio en la LOS (default 3 dB).

**Resultado Dual eNodeB:**
- En modo points (GeoJSON), cada punto muestra el color del **mejor servidor**:
  - Azul: servidor 1
  - Naranja: servidor 2
- Popup detallado incluye `server: "1"` o `server: "2"` y número de edificios en LOS.

### 8) Ejemplos de uso con Ray-Tracing y Dual eNodeB

**Ejemplo 1: Monocelda con ray-tracing**
```json
POST /api/simulate
{
  "lat": 40.4916,
  "lon": -3.7212,
  "lat2": null,
  "lon2": null,
  "frecuencia_mhz": 800,
  "radio_m": 500,
  "enable_los": true,
  "atenuacion_muro_db": 3.0,
  "output_mode": "points"
}
```

**Ejemplo 2: Dual eNodeB sin ray-tracing (solo path loss)**
```json
POST /api/simulate
{
  "lat": 40.4916,
  "lon": -3.7212,
  "lat2": 40.4850,
  "lon2": -3.7100,
  "frecuencia_mhz": 800,
  "radio_m": 500,
  "enable_los": false,
  "output_mode": "points"
}
```

**Ejemplo 3: Dual eNodeB con ray-tracing y atenuación variable**
```json
POST /api/simulate
{
  "lat": 40.4916,
  "lon": -3.7212,
  "lat2": 40.4850,
  "lon2": -3.7100,
  "frecuencia_mhz": 1800,
  "radio_m": 500,
  "enable_los": true,
  "atenuacion_muro_db": 5.0,
  "output_mode": "raster"
}
```

### 9) Visualización Avanzada: Hex-Binning con Interpolación IDW

**¿Por qué Hex-Binning?**
- Los puntos discretos son académicamente precisos pero profesionalmente poco legibles.
- Hex-Binning interpola el RSRP usando IDW (Inverse Distance Weighting) sobre una malla hexagonal continua.
- Estándar en herramientas profesionales de RF Planning (Atoll, Mentum Planet, Ranplan).

**Cómo funciona:**
1. **Frontend (Turf.js)**: Tras recibir los puntos GeoJSON del backend:
  - Crea una malla hexagonal sobre el área de análisis usando `turf.hexGrid()`
  - Para cada hexágono, interpola RSRP usando IDW: $$RSRP_{hex} = \frac{\sum_{i} w_i \times RSRP_i}{\sum_{i} w_i} \quad \text{donde} \quad w_i = \frac{1}{d_i^2}$$
  - Determina el servidor dominante en cada hexágono (mayoría de puntos)
  - Colorea según RSRP interpolado (gradiente: rojo oscuro → naranja → amarillo → verde)

2. **Modos de visualización:**
  - **Puntos discretos**: Render original, rápido, académico
  - **Hex-Binning**: Superficie continua, profesional, ideal para decisiones de despliegue

3. **Interactividad:**
  - Clic en hexágono → popup con:
    - RSRP interpolado (dBm)
    - Mejor servidor (eNodeB 1 o 2)
    - Número de puntos en la celda

4. **Paleta de colores RSRP:**
  | Rango | Color | Calidad |
  |-------|-------|---------|
  | RSRP > -80 dBm | Verde oscuro | Excelente |
  | -80 ≥ RSRP > -90 dBm | Verde claro | Muy buena |
  | -90 ≥ RSRP > -100 dBm | Amarillo | Aceptable |
  | -100 ≥ RSRP > -110 dBm | Naranja | Pobre |
  | RSRP ≤ -110 dBm | Rojo oscuro | Sin servicio |

### 10) Panel analítico en tiempo real (Chart.js)

Se añadió un gráfico lateral tipo **Doughnut** que resume automáticamente la distribución de calidad tras cada simulación.

- **Excelente**: `RSRP >= -90 dBm`
- **Aceptable**: `-105 dBm <= RSRP < -90 dBm`
- **Sin cobertura**: `RSRP < -105 dBm`

**Fuente de datos del gráfico:**
- Si la visualización está en **Hex-Binning**, el porcentaje se calcula sobre los hexágonos interpolados.
- Si está en **Puntos**, el porcentaje se calcula sobre los puntos discretos GeoJSON.
- En modo **Raster**, se usa el resumen agregado del backend.

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