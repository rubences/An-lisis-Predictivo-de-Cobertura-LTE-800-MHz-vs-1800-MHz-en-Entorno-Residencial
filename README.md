# Análisis Predictivo de Cobertura LTE: 800 MHz vs 1800 MHz

Comparativa de cobertura LTE en entorno residencial, combinando:
- modelo de propagación COST-231/Okumura-Hata,
- extracción geoespacial real desde OpenStreetMap (OSMnx),
- mapas de calor con umbral de servicio en **RSRP > -105 dBm**.

## Qué hace el script

Al ejecutar `python cobertura_lte.py`:
1. Descarga un barrio real (`Mirasierra, Madrid, Spain`) con su red viaria y edificios desde OSM.
2. Define un eNodeB virtual en coordenadas lat/lon configurables.
3. Calcula Path Loss y RSRP para **800 MHz** y **1800 MHz** sobre puntos de calle.
4. Genera heatmaps geoespaciales y una comparativa de ventaja de 800 frente a 1800.
5. Emite un informe con recomendación de despliegue (cobertura vs capacidad).

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

## Salidas en `resultados/`

- `figura1_perdida_trayecto.png`
- `figura2_rsrp_vs_distancia.png`
- `figura3_radios_cobertura.png`
- `figura4_mapa_cobertura_2d.png`
- `figura5_diferencia_cobertura.png`
- `figura6_perdida_vs_frecuencia.png`
- `figura7_heatmap_geoespacial.png`
- `figura8_delta_geoespacial.png`
- `tabla_cobertura.csv`
- `tabla_cobertura_geoespacial.csv`

## Criterio operativo en mapas

- **Cobertura válida**: `RSRP > -105 dBm`
- **Zona ciega**: `RSRP < -105 dBm`

En los heatmaps, el colormap está centrado en `-105 dBm` para separar visualmente ambas zonas.

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