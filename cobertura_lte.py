"""
Análisis Predictivo de Cobertura LTE: 800 MHz vs 1800 MHz en Entorno Residencial
==================================================================================
Implementa el modelo de propagación COST-231 Hata (y el modelo Okumura-Hata
extendido) para comparar la cobertura de dos portadoras LTE en un barrio
residencial con calles estrechas y edificaciones de 4-6 plantas.

Uso:
    python cobertura_lte.py

Los resultados (figuras) se guardan automáticamente en la carpeta resultados/.
"""

import os
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")          # backend sin pantalla
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import pandas as pd

# ---------------------------------------------------------------------------
# Parámetros del escenario residencial
# ---------------------------------------------------------------------------

SCENARIO = {
    "nombre": "Barrio Residencial – Calles Estrechas",
    "altura_edificios_m": 15,        # ~4-6 plantas ≈ 12-18 m → valor central 15 m
    "altura_bs_m": 25,               # Altura antena de la estación base (m)
    "altura_movil_m": 1.5,           # Altura del terminal móvil (m)
    "distancia_min_km": 0.1,         # Distancia mínima de análisis (km)
    "distancia_max_km": 5.0,         # Distancia máxima de análisis (km)
    "num_puntos": 500,               # Puntos en el eje de distancia
}

# Parámetros del enlace (link budget) para ambas bandas
# Los valores son representativos de una celda macro LTE urbana.
LINK_BUDGET = {
    "potencia_tx_dbm": 43,           # Potencia transmitida por la BS (dBm)
    "ganancia_antena_bs_dbi": 17,    # Ganancia antena BS (dBi)
    "perdidas_cable_db": 2,          # Pérdidas de cable/conectores (dB)
    "ganancia_antena_ue_dbi": 0,     # Ganancia antena terminal (dBi, omnidireccional)
    "figura_ruido_ue_db": 7,         # Figura de ruido del terminal (dB)
    "margen_interferencia_db": 3,    # Margen de interferencia (dB)
    "margen_desvanecimiento_db": 8,  # Margen de desvanecimiento (dB)
    "perdidas_penetracion_db": 15,   # Pérdidas de penetración en edificios (dB)
}

# Umbrales de calidad de servicio LTE (RSRP en dBm)
QOS_THRESHOLDS = {
    "excelente": -80,
    "buena": -90,
    "aceptable": -100,   # mínimo para videollamadas y streaming
    "pobre": -110,
    "sin_servicio": -120,
}

# Bandas LTE a comparar
BANDS = {
    "800 MHz": {
        "frecuencia_mhz": 800,
        "color": "#1a6faf",
        "linestyle": "-",
        "label": "LTE 800 MHz (Banda 20)",
    },
    "1800 MHz": {
        "frecuencia_mhz": 1800,
        "color": "#e05c1a",
        "linestyle": "--",
        "label": "LTE 1800 MHz (Banda 3)",
    },
}

# ---------------------------------------------------------------------------
# Modelos de propagación
# ---------------------------------------------------------------------------


def _factor_correccion_altura_movil(frecuencia_mhz: float, altura_movil_m: float) -> float:
    """Factor de corrección de altura del terminal a(hm) para entorno urbano.

    Para grandes ciudades (fc > 300 MHz):
        a(hm) = 3.2 * (log10(11.75 * hm))^2 - 4.97

    Para ciudades medianas/pequeñas o entornos suburbanos (fc ≤ 300 MHz):
        a(hm) = (1.1 * log10(fc) - 0.7) * hm - (1.56 * log10(fc) - 0.8)
    """
    if frecuencia_mhz > 300:
        return 3.2 * (math.log10(11.75 * altura_movil_m)) ** 2 - 4.97
    return (1.1 * math.log10(frecuencia_mhz) - 0.7) * altura_movil_m - (
        1.56 * math.log10(frecuencia_mhz) - 0.8
    )


def hata_urbano(
    frecuencia_mhz: float,
    distancia_km: float,
    altura_bs_m: float,
    altura_movil_m: float,
) -> float:
    """Modelo Okumura-Hata para entorno urbano (150-1500 MHz).

    L_50 [dB] = 69.55 + 26.16·log(fc) – 13.82·log(hb) – a(hm)
                + (44.9 – 6.55·log(hb))·log(d)

    Parámetros
    ----------
    frecuencia_mhz : frecuencia portadora en MHz
    distancia_km   : distancia BS-terminal en km
    altura_bs_m    : altura de la antena de la BS en metros
    altura_movil_m : altura del terminal móvil en metros

    Devuelve
    --------
    Pérdida de trayecto en dB
    """
    if not (150 <= frecuencia_mhz <= 1500):
        raise ValueError(
            f"El modelo Hata es válido entre 150 y 1500 MHz. Se recibió {frecuencia_mhz} MHz."
        )
    a_hm = _factor_correccion_altura_movil(frecuencia_mhz, altura_movil_m)
    return (
        69.55
        + 26.16 * math.log10(frecuencia_mhz)
        - 13.82 * math.log10(altura_bs_m)
        - a_hm
        + (44.9 - 6.55 * math.log10(altura_bs_m)) * math.log10(distancia_km)
    )


def cost231_hata(
    frecuencia_mhz: float,
    distancia_km: float,
    altura_bs_m: float,
    altura_movil_m: float,
    entorno: str = "urbano",
) -> float:
    """Modelo COST-231 Hata para entorno urbano (1500-2000 MHz).

    L_50 [dB] = 46.3 + 33.9·log(fc) – 13.82·log(hb) – a(hm)
                + (44.9 – 6.55·log(hb))·log(d) + C_m

    C_m = 0 dB (ciudades medianas/suburbano), 3 dB (metrópoli densa)

    Parámetros
    ----------
    frecuencia_mhz : frecuencia portadora en MHz
    distancia_km   : distancia BS-terminal en km
    altura_bs_m    : altura de la antena de la BS en metros
    altura_movil_m : altura del terminal móvil en metros
    entorno        : "urbano" → C_m = 3, "suburbano" → C_m = 0

    Devuelve
    --------
    Pérdida de trayecto en dB
    """
    if not (1500 <= frecuencia_mhz <= 2000):
        raise ValueError(
            f"El modelo COST-231 Hata es válido entre 1500 y 2000 MHz. Se recibió {frecuencia_mhz} MHz."
        )
    a_hm = _factor_correccion_altura_movil(frecuencia_mhz, altura_movil_m)
    cm = 3.0 if entorno == "urbano" else 0.0
    return (
        46.3
        + 33.9 * math.log10(frecuencia_mhz)
        - 13.82 * math.log10(altura_bs_m)
        - a_hm
        + (44.9 - 6.55 * math.log10(altura_bs_m)) * math.log10(distancia_km)
        + cm
    )


def perdida_trayecto(
    frecuencia_mhz: float,
    distancia_km: float,
    altura_bs_m: float,
    altura_movil_m: float,
    entorno: str = "urbano",
) -> float:
    """Selecciona automáticamente el modelo según la frecuencia.

    - Hata (Okumura-Hata): 150-1500 MHz
    - COST-231 Hata: 1500-2000 MHz
    """
    if frecuencia_mhz <= 1500:
        return hata_urbano(frecuencia_mhz, distancia_km, altura_bs_m, altura_movil_m)
    return cost231_hata(
        frecuencia_mhz, distancia_km, altura_bs_m, altura_movil_m, entorno
    )


# ---------------------------------------------------------------------------
# Link budget y cálculo de RSRP
# ---------------------------------------------------------------------------


def eirp_dbm(lb: dict) -> float:
    """Potencia Isotrópica Radiada Equivalente (EIRP) de la BS en dBm."""
    return lb["potencia_tx_dbm"] + lb["ganancia_antena_bs_dbi"] - lb["perdidas_cable_db"]


def rsrp_dbm(
    frecuencia_mhz: float,
    distancia_km: float,
    scenario: dict,
    link_budget: dict,
    incluir_penetracion: bool = True,
    entorno: str = "urbano",
) -> float:
    """Calcula el RSRP (Reference Signal Received Power) en dBm.

    RSRP = EIRP – PL + Ganancia_antena_UE
           – Margen_desvanecimiento – Margen_interferencia
           [– Pérdidas_penetración  (si incluir_penetracion=True)]
    """
    lp = perdida_trayecto(
        frecuencia_mhz,
        distancia_km,
        scenario["altura_bs_m"],
        scenario["altura_movil_m"],
        entorno,
    )
    rx = (
        eirp_dbm(link_budget)
        - lp
        + link_budget["ganancia_antena_ue_dbi"]
        - link_budget["margen_desvanecimiento_db"]
        - link_budget["margen_interferencia_db"]
    )
    if incluir_penetracion:
        rx -= link_budget["perdidas_penetracion_db"]
    return rx


def radio_cobertura_km(
    frecuencia_mhz: float,
    umbral_dbm: float,
    scenario: dict,
    link_budget: dict,
    incluir_penetracion: bool = True,
    entorno: str = "urbano",
    d_min: float = 0.05,
    d_max: float = 20.0,
    tolerancia: float = 0.01,
) -> float:
    """Radio máximo de cobertura (en km) para un umbral RSRP dado.

    Utiliza búsqueda binaria sobre la función RSRP(d).
    """
    def objetivo(d):
        return rsrp_dbm(
            frecuencia_mhz, d, scenario, link_budget, incluir_penetracion, entorno
        ) - umbral_dbm

    # Si ni en d_min se supera el umbral, la celda no cubre
    if objetivo(d_min) < 0:
        return 0.0

    # Si en d_max aún supera el umbral, el radio supera nuestro límite
    if objetivo(d_max) >= 0:
        return d_max

    lo, hi = d_min, d_max
    while (hi - lo) > tolerancia:
        mid = (lo + hi) / 2.0
        if objetivo(mid) >= 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# ---------------------------------------------------------------------------
# Generación de resultados y figuras
# ---------------------------------------------------------------------------


def calcular_tabla_resumen(scenario: dict, lb: dict, entorno: str = "urbano") -> pd.DataFrame:
    """Genera una tabla comparativa para ambas bandas con distintos umbrales."""
    filas = []
    for nombre_banda, cfg in BANDS.items():
        fc = cfg["frecuencia_mhz"]
        for nombre_umbral, umbral in QOS_THRESHOLDS.items():
            r_exterior = radio_cobertura_km(fc, umbral, scenario, lb, False, entorno)
            r_interior = radio_cobertura_km(fc, umbral, scenario, lb, True, entorno)
            area_exterior = math.pi * r_exterior**2
            area_interior = math.pi * r_interior**2
            filas.append(
                {
                    "Banda": nombre_banda,
                    "Umbral": nombre_umbral,
                    "RSRP (dBm)": umbral,
                    "Radio exterior (km)": round(r_exterior, 3),
                    "Área exterior (km²)": round(area_exterior, 3),
                    "Radio interior (km)": round(r_interior, 3),
                    "Área interior (km²)": round(area_interior, 3),
                }
            )
    return pd.DataFrame(filas)


def _clasificar_rsrp(rsrp: float) -> str:
    """Devuelve la categoría de calidad para un valor RSRP dado."""
    if rsrp >= QOS_THRESHOLDS["excelente"]:
        return "excelente"
    if rsrp >= QOS_THRESHOLDS["buena"]:
        return "buena"
    if rsrp >= QOS_THRESHOLDS["aceptable"]:
        return "aceptable"
    if rsrp >= QOS_THRESHOLDS["pobre"]:
        return "pobre"
    return "sin_servicio"


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------


def figura_perdida_trayecto(scenario: dict, output_dir: str) -> None:
    """Figura 1: Pérdida de trayecto vs. distancia para ambas bandas."""
    distancias = np.linspace(
        scenario["distancia_min_km"], scenario["distancia_max_km"], scenario["num_puntos"]
    )

    fig, ax = plt.subplots(figsize=(10, 6))
    for nombre_banda, cfg in BANDS.items():
        fc = cfg["frecuencia_mhz"]
        lp = [
            perdida_trayecto(fc, d, scenario["altura_bs_m"], scenario["altura_movil_m"])
            for d in distancias
        ]
        ax.plot(
            distancias,
            lp,
            color=cfg["color"],
            linestyle=cfg["linestyle"],
            linewidth=2,
            label=cfg["label"],
        )

    ax.set_xlabel("Distancia a la estación base (km)", fontsize=12)
    ax.set_ylabel("Pérdida de trayecto (dB)", fontsize=12)
    ax.set_title(
        "Modelo de Propagación COST-231 Hata / Okumura-Hata\n"
        f"Entorno: {scenario['nombre']}",
        fontsize=13,
    )
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.4)
    ax.set_xlim(left=0)
    plt.tight_layout()
    path = os.path.join(output_dir, "figura1_perdida_trayecto.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  ✔ Guardada: {path}")


def figura_rsrp_vs_distancia(
    scenario: dict, lb: dict, output_dir: str, entorno: str = "urbano"
) -> None:
    """Figura 2: RSRP vs. distancia (exterior e interior) para ambas bandas."""
    distancias = np.linspace(
        scenario["distancia_min_km"], scenario["distancia_max_km"], scenario["num_puntos"]
    )

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    titulos = ["Exterior (sin penetración)", "Interior (con penetración)"]
    flags_penetracion = [False, True]

    for ax, incluir_penet, titulo in zip(axes, flags_penetracion, titulos):
        for nombre_banda, cfg in BANDS.items():
            fc = cfg["frecuencia_mhz"]
            rsrp = [
                rsrp_dbm(fc, d, scenario, lb, incluir_penet, entorno)
                for d in distancias
            ]
            ax.plot(
                distancias,
                rsrp,
                color=cfg["color"],
                linestyle=cfg["linestyle"],
                linewidth=2,
                label=cfg["label"],
            )

        # Líneas de umbral
        colores_umbral = {
            "excelente": "green",
            "buena": "limegreen",
            "aceptable": "gold",
            "pobre": "orange",
            "sin_servicio": "red",
        }
        for nombre_umbral, valor_umbral in QOS_THRESHOLDS.items():
            ax.axhline(
                valor_umbral,
                color=colores_umbral[nombre_umbral],
                linestyle=":",
                linewidth=1.2,
                alpha=0.85,
                label=f"Umbral {nombre_umbral} ({valor_umbral} dBm)",
            )

        ax.set_xlabel("Distancia a la BS (km)", fontsize=11)
        ax.set_ylabel("RSRP (dBm)", fontsize=11)
        ax.set_title(f"RSRP – {titulo}", fontsize=12)
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(True, alpha=0.4)
        ax.set_xlim(left=0)
        ax.set_ylim(-140, -40)

    fig.suptitle(
        f"Comparativa de RSRP: LTE 800 MHz vs 1800 MHz\n{scenario['nombre']}",
        fontsize=13,
        fontweight="bold",
    )
    plt.tight_layout()
    path = os.path.join(output_dir, "figura2_rsrp_vs_distancia.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  ✔ Guardada: {path}")


def figura_radios_cobertura(
    scenario: dict, lb: dict, output_dir: str, entorno: str = "urbano"
) -> None:
    """Figura 3: Radios de cobertura para cada umbral de servicio (barras agrupadas)."""
    nombres_umbral = list(QOS_THRESHOLDS.keys())
    valores_umbral = list(QOS_THRESHOLDS.values())
    n = len(nombres_umbral)
    x = np.arange(n)
    ancho = 0.35

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    escenarios_penet = [
        (False, "Exterior (sin penetración)"),
        (True, "Interior (con penetración)"),
    ]

    for ax, (incluir_penet, titulo) in zip(axes, escenarios_penet):
        for i, (nombre_banda, cfg) in enumerate(BANDS.items()):
            fc = cfg["frecuencia_mhz"]
            radios = [
                radio_cobertura_km(fc, u, scenario, lb, incluir_penet, entorno)
                for u in valores_umbral
            ]
            offset = (i - 0.5) * ancho
            bars = ax.bar(
                x + offset,
                radios,
                ancho,
                label=cfg["label"],
                color=cfg["color"],
                alpha=0.85,
                edgecolor="white",
            )
            # Etiquetas sobre las barras
            for bar, val in zip(bars, radios):
                if val > 0:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.03,
                        f"{val:.2f}",
                        ha="center",
                        va="bottom",
                        fontsize=8,
                    )

        etiquetas = [f"{n}\n({v} dBm)" for n, v in zip(nombres_umbral, valores_umbral)]
        ax.set_xticks(x)
        ax.set_xticklabels(etiquetas, fontsize=9)
        ax.set_ylabel("Radio de cobertura (km)", fontsize=11)
        ax.set_title(titulo, fontsize=12)
        ax.legend(fontsize=10)
        ax.grid(axis="y", alpha=0.4)

    fig.suptitle(
        "Radio de Cobertura por Umbral de Servicio\nLTE 800 MHz vs 1800 MHz",
        fontsize=13,
        fontweight="bold",
    )
    plt.tight_layout()
    path = os.path.join(output_dir, "figura3_radios_cobertura.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  ✔ Guardada: {path}")


def figura_mapa_cobertura_2d(
    scenario: dict, lb: dict, output_dir: str, entorno: str = "urbano"
) -> None:
    """Figura 4: Mapa de cobertura 2D con calidad de señal (vista aérea simplificada)."""
    r_max = 3.0  # km visibles en el mapa
    n_puntos = 300
    x = np.linspace(-r_max, r_max, n_puntos)
    y = np.linspace(-r_max, r_max, n_puntos)
    X, Y = np.meshgrid(x, y)
    D = np.sqrt(X**2 + Y**2)
    D = np.where(D < scenario["distancia_min_km"], scenario["distancia_min_km"], D)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Mapa de colores: verde(excelente) → amarillo(aceptable) → rojo(sin servicio)
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "cobertura",
        ["#7f0000", "#d62728", "#ff7f0e", "#ffdd57", "#2ca02c", "#1a6faf"],
        N=256,
    )
    cmap.set_under("lightgrey")

    for ax, (nombre_banda, cfg) in zip(axes, BANDS.items()):
        fc = cfg["frecuencia_mhz"]
        # Vectorizado usando numpy (aplicamos la fórmula directamente)
        with np.errstate(divide="ignore", invalid="ignore"):
            lp = np.vectorize(
                lambda d: perdida_trayecto(
                    fc, d, scenario["altura_bs_m"], scenario["altura_movil_m"]
                )
            )(D)
        rsrp_map = (
            eirp_dbm(lb)
            - lp
            + lb["ganancia_antena_ue_dbi"]
            - lb["margen_desvanecimiento_db"]
            - lb["margen_interferencia_db"]
            - lb["perdidas_penetracion_db"]
        )

        im = ax.contourf(
            X,
            Y,
            rsrp_map,
            levels=[-140, -120, -110, -100, -90, -80, -40],
            cmap=cmap,
            vmin=-120,
            vmax=-40,
        )
        # Círculo de la BS
        ax.plot(0, 0, "k^", markersize=10, label="Estación Base", zorder=5)
        # Contorno del umbral "aceptable" (-100 dBm) como línea de servicio mínimo
        cs = ax.contour(
            X,
            Y,
            rsrp_map,
            levels=[QOS_THRESHOLDS["aceptable"]],
            colors=["white"],
            linewidths=2,
            linestyles="--",
        )
        ax.clabel(cs, fmt=f"{QOS_THRESHOLDS['aceptable']} dBm", fontsize=9, colors="white")

        ax.set_xlabel("Distancia Este-Oeste (km)", fontsize=10)
        ax.set_ylabel("Distancia Norte-Sur (km)", fontsize=10)
        ax.set_title(f"Mapa de cobertura interior\n{cfg['label']}", fontsize=11)
        ax.legend(loc="upper right", fontsize=9)
        ax.set_aspect("equal")

        cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("RSRP (dBm)", fontsize=9)
        cbar.set_ticks([-120, -110, -100, -90, -80])
        cbar.set_ticklabels(
            ["−120 (sin serv.)", "−110 (pobre)", "−100 (acept.)", "−90 (buena)", "−80 (excel.)"]
        )

    fig.suptitle(
        f"Mapa de Cobertura Interior (con pérdidas de penetración)\n{scenario['nombre']}",
        fontsize=13,
        fontweight="bold",
    )
    plt.tight_layout()
    path = os.path.join(output_dir, "figura4_mapa_cobertura_2d.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  ✔ Guardada: {path}")


def figura_diferencia_cobertura(
    scenario: dict, lb: dict, output_dir: str, entorno: str = "urbano"
) -> None:
    """Figura 5: Diferencia de RSRP (800 MHz – 1800 MHz) vs. distancia."""
    distancias = np.linspace(
        scenario["distancia_min_km"], scenario["distancia_max_km"], scenario["num_puntos"]
    )

    fc_800 = BANDS["800 MHz"]["frecuencia_mhz"]
    fc_1800 = BANDS["1800 MHz"]["frecuencia_mhz"]

    diff_exterior = np.array(
        [
            rsrp_dbm(fc_800, d, scenario, lb, False, entorno)
            - rsrp_dbm(fc_1800, d, scenario, lb, False, entorno)
            for d in distancias
        ]
    )
    diff_interior = np.array(
        [
            rsrp_dbm(fc_800, d, scenario, lb, True, entorno)
            - rsrp_dbm(fc_1800, d, scenario, lb, True, entorno)
            for d in distancias
        ]
    )

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(
        distancias,
        diff_exterior,
        color="#1a6faf",
        linewidth=2,
        label="Exterior (sin penetración)",
    )
    ax.plot(
        distancias,
        diff_interior,
        color="#e05c1a",
        linestyle="--",
        linewidth=2,
        label="Interior (con penetración)",
    )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.fill_between(
        distancias,
        diff_exterior,
        0,
        where=(diff_exterior > 0),
        alpha=0.15,
        color="#1a6faf",
        label="Ventaja 800 MHz",
    )

    ax.set_xlabel("Distancia a la BS (km)", fontsize=12)
    ax.set_ylabel("Diferencia de RSRP (dB)\n[800 MHz − 1800 MHz]", fontsize=11)
    ax.set_title(
        "Ventaja de la Banda 800 MHz sobre la Banda 1800 MHz\nen función de la distancia",
        fontsize=13,
    )
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.4)
    ax.set_xlim(left=0)
    plt.tight_layout()
    path = os.path.join(output_dir, "figura5_diferencia_cobertura.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  ✔ Guardada: {path}")


def figura_ganancia_frecuencia(output_dir: str) -> None:
    """Figura 6: Ganancia de propagación libre por diferencia de frecuencia."""
    frecuencias = np.linspace(700, 2000, 500)
    distancia_ref = 1.0  # km

    perdidas = [
        perdida_trayecto(
            f,
            distancia_ref,
            SCENARIO["altura_bs_m"],
            SCENARIO["altura_movil_m"],
        )
        for f in frecuencias
    ]

    # Referencia: pérdida a 800 MHz
    lp_800 = perdida_trayecto(
        800, distancia_ref, SCENARIO["altura_bs_m"], SCENARIO["altura_movil_m"]
    )
    lp_1800 = perdida_trayecto(
        1800, distancia_ref, SCENARIO["altura_bs_m"], SCENARIO["altura_movil_m"]
    )

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(frecuencias, perdidas, color="#444", linewidth=2)
    ax.axvline(800, color=BANDS["800 MHz"]["color"], linestyle="--", linewidth=1.8, label="800 MHz")
    ax.axvline(
        1800, color=BANDS["1800 MHz"]["color"], linestyle="--", linewidth=1.8, label="1800 MHz"
    )
    ax.annotate(
        f"{lp_800:.1f} dB",
        xy=(800, lp_800),
        xytext=(850, lp_800 - 4),
        arrowprops=dict(arrowstyle="->", color=BANDS["800 MHz"]["color"]),
        color=BANDS["800 MHz"]["color"],
        fontsize=10,
    )
    ax.annotate(
        f"{lp_1800:.1f} dB",
        xy=(1800, lp_1800),
        xytext=(1600, lp_1800 + 3),
        arrowprops=dict(arrowstyle="->", color=BANDS["1800 MHz"]["color"]),
        color=BANDS["1800 MHz"]["color"],
        fontsize=10,
    )
    ax.set_xlabel("Frecuencia (MHz)", fontsize=12)
    ax.set_ylabel("Pérdida de trayecto a 1 km (dB)", fontsize=11)
    ax.set_title(
        "Pérdida de Trayecto en Función de la Frecuencia (d = 1 km)\n"
        f"Entorno: {SCENARIO['nombre']}",
        fontsize=12,
    )
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.4)
    plt.tight_layout()
    path = os.path.join(output_dir, "figura6_perdida_vs_frecuencia.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  ✔ Guardada: {path}")


# ---------------------------------------------------------------------------
# Informe de texto
# ---------------------------------------------------------------------------


def imprimir_informe(scenario: dict, lb: dict, entorno: str = "urbano") -> None:
    """Imprime por consola el resumen ejecutivo del análisis."""
    separador = "=" * 70
    print(f"\n{separador}")
    print("  ESTUDIO PRELIMINAR DE COBERTURA LTE")
    print(f"  Escenario: {scenario['nombre']}")
    print(separador)

    print("\n── Parámetros del enlace ──")
    print(f"  EIRP de la BS       : {eirp_dbm(lb):.1f} dBm")
    print(f"  Altura antena BS    : {scenario['altura_bs_m']} m")
    print(f"  Altura terminal     : {scenario['altura_movil_m']} m")
    print(f"  Pérd. penetración   : {lb['perdidas_penetracion_db']} dB")
    print(f"  Margen desvane.     : {lb['margen_desvanecimiento_db']} dB")
    print(f"  Margen interferencia: {lb['margen_interferencia_db']} dB")

    print("\n── Tabla de radios de cobertura ──")
    tabla = calcular_tabla_resumen(scenario, lb, entorno)
    # Mostrar solo las columnas clave
    cols = ["Banda", "Umbral", "RSRP (dBm)", "Radio exterior (km)", "Radio interior (km)"]
    print(tabla[cols].to_string(index=False))

    print("\n── Comparativa clave (umbral de servicio aceptable: −100 dBm) ──")
    for nombre_banda, cfg in BANDS.items():
        fc = cfg["frecuencia_mhz"]
        r_ext = radio_cobertura_km(fc, QOS_THRESHOLDS["aceptable"], scenario, lb, False, entorno)
        r_int = radio_cobertura_km(fc, QOS_THRESHOLDS["aceptable"], scenario, lb, True, entorno)
        area_ext = math.pi * r_ext**2
        area_int = math.pi * r_int**2
        print(f"\n  {cfg['label']}")
        print(f"    Radio exterior  : {r_ext:.3f} km  →  Área: {area_ext:.2f} km²")
        print(f"    Radio interior  : {r_int:.3f} km  →  Área: {area_int:.2f} km²")

    # Ratio de cobertura 800 vs 1800 MHz
    r_800 = radio_cobertura_km(
        800, QOS_THRESHOLDS["aceptable"], scenario, lb, True, entorno
    )
    r_1800 = radio_cobertura_km(
        1800, QOS_THRESHOLDS["aceptable"], scenario, lb, True, entorno
    )
    if r_1800 > 0:
        ratio_radio = r_800 / r_1800
        ratio_area = (r_800 / r_1800) ** 2
        print(
            f"\n  ➤ La banda de 800 MHz alcanza {ratio_radio:.2f}× el radio"
            f" y {ratio_area:.2f}× el área de la de 1800 MHz"
        )
        print(
            f"  ➤ Para cubrir el mismo barrio se necesitarían ~{ratio_area:.1f}×"
            " más celdas de 1800 MHz que de 800 MHz"
        )

    print(
        "\n── Recomendación ──\n"
        "  • Use la banda de 800 MHz como capa de COBERTURA (indoor y zonas alejadas).\n"
        "  • Use la banda de 1800 MHz como capa de CAPACIDAD (áreas densas, interior\n"
        "    de edificios dentro del radio próximo a la BS).\n"
        "  • Para el servicio de videollamadas/streaming en interior se recomienda\n"
        "    un umbral mínimo de RSRP ≥ −100 dBm, cubierto principalmente por 800 MHz."
    )
    print(f"\n{separador}\n")


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


def main() -> None:
    output_dir = "resultados"
    os.makedirs(output_dir, exist_ok=True)

    print("Análisis Predictivo de Cobertura LTE – 800 MHz vs 1800 MHz")
    print(f"Entorno: {SCENARIO['nombre']}")
    print(f"Figuras exportadas a: {os.path.abspath(output_dir)}/\n")

    print("Generando figuras…")
    figura_perdida_trayecto(SCENARIO, output_dir)
    figura_rsrp_vs_distancia(SCENARIO, LINK_BUDGET, output_dir)
    figura_radios_cobertura(SCENARIO, LINK_BUDGET, output_dir)
    figura_mapa_cobertura_2d(SCENARIO, LINK_BUDGET, output_dir)
    figura_diferencia_cobertura(SCENARIO, LINK_BUDGET, output_dir)
    figura_ganancia_frecuencia(output_dir)

    imprimir_informe(SCENARIO, LINK_BUDGET)

    # Guardar tabla en CSV
    tabla = calcular_tabla_resumen(SCENARIO, LINK_BUDGET)
    csv_path = os.path.join(output_dir, "tabla_cobertura.csv")
    tabla.to_csv(csv_path, index=False)
    print(f"  ✔ Tabla guardada: {csv_path}\n")


if __name__ == "__main__":
    main()
