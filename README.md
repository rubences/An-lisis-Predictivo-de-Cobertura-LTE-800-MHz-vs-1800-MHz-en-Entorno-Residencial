# Análisis Predictivo de Cobertura LTE: 800 MHz vs 1800 MHz en Entorno Residencial

Herramienta de análisis y visualización para comparar la cobertura de dos
portadoras LTE —**800 MHz (Banda 20)** y **1800 MHz (Banda 3)**— en un barrio
residencial con calles estrechas y edificaciones de 4 a 6 plantas.

El núcleo del proyecto transforma el modelo matemático de propagación
**COST-231 Hata** (y su predecesor Okumura-Hata) en gráficas y tablas que
facilitan la toma de decisiones de despliegue para servicios críticos:
videollamadas, *streaming* y mensajería.

---

## Estructura del proyecto

```
.
├── cobertura_lte.py          # Script principal de análisis
├── requirements.txt          # Dependencias Python
├── tests/
│   └── test_cobertura_lte.py # Tests unitarios (pytest)
└── resultados/               # Figuras y CSV generados (se crea al ejecutar)
    ├── figura1_perdida_trayecto.png
    ├── figura2_rsrp_vs_distancia.png
    ├── figura3_radios_cobertura.png
    ├── figura4_mapa_cobertura_2d.png
    ├── figura5_diferencia_cobertura.png
    ├── figura6_perdida_vs_frecuencia.png
    └── tabla_cobertura.csv
```

---

## Instalación

```bash
pip install -r requirements.txt
```

---

## Uso

```bash
python cobertura_lte.py
```

El script:
1. Calcula la pérdida de trayecto y el RSRP para distancias de 0,1 a 5 km.
2. Estima el radio de cobertura para cinco umbrales de calidad de servicio.
3. Genera seis figuras PNG y un CSV en la carpeta `resultados/`.
4. Imprime por consola un informe ejecutivo con la recomendación de despliegue.

---

## Modelos de propagación implementados

| Frecuencia | Modelo              | Rango de validez  |
|------------|---------------------|-------------------|
| 800 MHz    | Okumura-Hata urbano | 150 – 1 500 MHz   |
| 1 800 MHz  | COST-231 Hata       | 1 500 – 2 000 MHz |

### Fórmula Okumura-Hata (urbano)

```
L₅₀ [dB] = 69,55 + 26,16·log(fc) – 13,82·log(hb) – a(hm)
            + (44,9 – 6,55·log(hb))·log(d)
```

### Fórmula COST-231 Hata (urbano)

```
L₅₀ [dB] = 46,3 + 33,9·log(fc) – 13,82·log(hb) – a(hm)
            + (44,9 – 6,55·log(hb))·log(d) + Cₘ   [Cₘ = 3 dB urbano]
```

donde:
- `fc` = frecuencia portadora (MHz)
- `hb` = altura de la antena de la BS (m)
- `hm` = altura del terminal móvil (m)
- `d`  = distancia BS–terminal (km)
- `a(hm)` = factor de corrección de altura del terminal

---

## Parámetros del escenario

| Parámetro                    | Valor            |
|------------------------------|------------------|
| Entorno                      | Barrio residencial, calles estrechas |
| Altura edificios              | ~15 m (4–6 plantas) |
| Altura antena BS             | 25 m             |
| Altura terminal móvil        | 1,5 m            |
| EIRP de la BS                | 58 dBm           |
| Pérdidas de penetración      | 15 dB            |
| Margen de desvanecimiento    | 8 dB             |
| Margen de interferencia      | 3 dB             |

---

## Umbrales de calidad de servicio (RSRP)

| Categoría      | RSRP (dBm) | Servicios garantizados               |
|---------------|------------|--------------------------------------|
| Excelente     | ≥ −80      | Todos los servicios                  |
| Buena         | ≥ −90      | Videollamadas HD, streaming 4K       |
| **Aceptable** | **≥ −100** | **Videollamadas, streaming, mensajería** |
| Pobre         | ≥ −110     | Solo mensajería / voz                |
| Sin servicio  | < −120     | —                                    |

---

## Resultados clave (umbral de servicio aceptable: −100 dBm)

| Banda     | Radio exterior | Área exterior | Radio interior | Área interior |
|-----------|---------------|---------------|---------------|--------------|
| 800 MHz   | 3,825 km      | 45,96 km²     | 1,458 km      | 6,67 km²     |
| 1 800 MHz | 1,536 km      | 7,41 km²      | 0,581 km      | 1,06 km²     |

> **La banda de 800 MHz cubre ~6,3× más área interior** que la de 1 800 MHz,
> lo que significa que se necesitarían aproximadamente 6 celdas de 1 800 MHz
> para igualar la cobertura de una sola celda de 800 MHz.

---

## Recomendación de despliegue

- **Capa de cobertura** → **800 MHz**: mayor alcance, mejor penetración en
  edificios, ideal para garantizar servicio en toda el área del barrio.
- **Capa de capacidad** → **1 800 MHz**: mayor ancho de banda disponible,
  recomendada para zonas densas y usuarios próximos a la BS.
- Para el umbral mínimo de videollamadas/streaming en interior
  (RSRP ≥ −100 dBm), la cobertura recae principalmente en la **banda de 800 MHz**.

---

## Tests

```bash
python -m pytest tests/ -v
```

Los tests validan la correcta implementación de los modelos matemáticos,
el cálculo del *link budget* y la estimación de radios de cobertura.