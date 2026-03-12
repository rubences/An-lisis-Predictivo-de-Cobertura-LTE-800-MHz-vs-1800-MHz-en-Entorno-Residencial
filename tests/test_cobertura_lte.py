"""
Tests unitarios para cobertura_lte.py
======================================
Valida la correcta implementación del modelo COST-231 Hata y Okumura-Hata,
el cálculo del link budget y la estimación de radios de cobertura.
"""

import math
import sys
import os
import pytest

# Añade la raíz del proyecto al path para importar el módulo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cobertura_lte import (
    _factor_correccion_altura_movil,
    hata_urbano,
    cost231_hata,
    perdida_trayecto,
    eirp_dbm,
    rsrp_dbm,
    radio_cobertura_km,
    calcular_tabla_resumen,
    SCENARIO,
    LINK_BUDGET,
    BANDS,
    QOS_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# Factor de corrección de altura del terminal
# ---------------------------------------------------------------------------


class TestFactorCorreccionAlturaMobil:
    def test_fc_mayor_300_MHz(self):
        """Para fc > 300 MHz usa la fórmula de ciudad grande."""
        hm = 1.5
        resultado = _factor_correccion_altura_movil(800, hm)
        esperado = 3.2 * (math.log10(11.75 * hm)) ** 2 - 4.97
        assert abs(resultado - esperado) < 1e-10

    def test_fc_menor_igual_300_MHz(self):
        """Para fc ≤ 300 MHz usa la fórmula de ciudad mediana."""
        fc = 200
        hm = 1.5
        resultado = _factor_correccion_altura_movil(fc, hm)
        esperado = (1.1 * math.log10(fc) - 0.7) * hm - (1.56 * math.log10(fc) - 0.8)
        assert abs(resultado - esperado) < 1e-10

    def test_valor_tipico_800mhz_1_5m(self):
        """Verifica un valor conocido para 800 MHz y hm=1.5 m."""
        # a(hm) = 3.2 * (log10(11.75 * 1.5))^2 - 4.97
        hm = 1.5
        a = 3.2 * (math.log10(11.75 * hm)) ** 2 - 4.97
        assert abs(_factor_correccion_altura_movil(800, hm) - a) < 1e-10

    def test_altura_movil_returns_float(self):
        """El factor de corrección de altura devuelve un número en coma flotante."""
        resultado = _factor_correccion_altura_movil(1800, 1.5)
        assert isinstance(resultado, float)


# ---------------------------------------------------------------------------
# Modelo Okumura-Hata
# ---------------------------------------------------------------------------


class TestHataUrbano:
    def test_rango_frecuencia_valido(self):
        """No debe lanzar excepción para fc en [150, 1500] MHz."""
        lp = hata_urbano(900, 1.0, 30, 1.5)
        assert lp > 0

    def test_rango_frecuencia_invalido_alto(self):
        """Debe lanzar ValueError para fc > 1500 MHz."""
        with pytest.raises(ValueError):
            hata_urbano(1800, 1.0, 30, 1.5)

    def test_rango_frecuencia_invalido_bajo(self):
        """Debe lanzar ValueError para fc < 150 MHz."""
        with pytest.raises(ValueError):
            hata_urbano(100, 1.0, 30, 1.5)

    def test_perdida_crece_con_distancia(self):
        """La pérdida de trayecto debe aumentar con la distancia."""
        lp_1km = hata_urbano(800, 1.0, 25, 1.5)
        lp_2km = hata_urbano(800, 2.0, 25, 1.5)
        assert lp_2km > lp_1km

    def test_perdida_crece_con_frecuencia(self):
        """A igual distancia, 1500 MHz tiene mayor pérdida que 300 MHz."""
        lp_baja = hata_urbano(300, 1.0, 25, 1.5)
        lp_alta = hata_urbano(1500, 1.0, 25, 1.5)
        assert lp_alta > lp_baja

    def test_perdida_decrece_altura_bs(self):
        """Mayor altura de BS debe reducir la pérdida de trayecto."""
        lp_bajo = hata_urbano(900, 2.0, 20, 1.5)
        lp_alto = hata_urbano(900, 2.0, 40, 1.5)
        assert lp_alto < lp_bajo

    def test_valor_conocido_900mhz(self):
        """Comprueba un valor de referencia calculado manualmente para 900 MHz."""
        fc, d, hb, hm = 900, 1.0, 30.0, 1.5
        a_hm = 3.2 * (math.log10(11.75 * hm)) ** 2 - 4.97
        lp_esperado = (
            69.55
            + 26.16 * math.log10(fc)
            - 13.82 * math.log10(hb)
            - a_hm
            + (44.9 - 6.55 * math.log10(hb)) * math.log10(d)
        )
        assert abs(hata_urbano(fc, d, hb, hm) - lp_esperado) < 1e-8


# ---------------------------------------------------------------------------
# Modelo COST-231 Hata
# ---------------------------------------------------------------------------


class TestCost231Hata:
    def test_rango_frecuencia_valido(self):
        """No debe lanzar excepción para fc en [1500, 2000] MHz."""
        lp = cost231_hata(1800, 1.0, 30, 1.5)
        assert lp > 0

    def test_rango_frecuencia_invalido_bajo(self):
        """Debe lanzar ValueError para fc < 1500 MHz."""
        with pytest.raises(ValueError):
            cost231_hata(900, 1.0, 30, 1.5)

    def test_rango_frecuencia_invalido_alto(self):
        """Debe lanzar ValueError para fc > 2000 MHz."""
        with pytest.raises(ValueError):
            cost231_hata(2100, 1.0, 30, 1.5)

    def test_perdida_crece_con_distancia(self):
        """La pérdida de trayecto debe aumentar con la distancia."""
        lp_1km = cost231_hata(1800, 1.0, 25, 1.5)
        lp_3km = cost231_hata(1800, 3.0, 25, 1.5)
        assert lp_3km > lp_1km

    def test_entorno_urbano_mayor_que_suburbano(self):
        """Entorno urbano (Cm=3) debe dar mayor pérdida que suburbano (Cm=0)."""
        lp_urbano = cost231_hata(1800, 2.0, 25, 1.5, "urbano")
        lp_sub = cost231_hata(1800, 2.0, 25, 1.5, "suburbano")
        assert abs(lp_urbano - lp_sub - 3.0) < 1e-8

    def test_valor_conocido_1800mhz(self):
        """Comprueba un valor de referencia calculado manualmente para 1800 MHz."""
        fc, d, hb, hm = 1800, 1.0, 30.0, 1.5
        a_hm = 3.2 * (math.log10(11.75 * hm)) ** 2 - 4.97
        lp_esperado = (
            46.3
            + 33.9 * math.log10(fc)
            - 13.82 * math.log10(hb)
            - a_hm
            + (44.9 - 6.55 * math.log10(hb)) * math.log10(d)
            + 3.0  # Cm urbano
        )
        assert abs(cost231_hata(fc, d, hb, hm, "urbano") - lp_esperado) < 1e-8


# ---------------------------------------------------------------------------
# Selección automática de modelo
# ---------------------------------------------------------------------------


class TestPerdidaTrayecto:
    def test_usa_hata_para_800mhz(self):
        """perdida_trayecto con 800 MHz debe coincidir con hata_urbano."""
        lp_auto = perdida_trayecto(800, 1.0, 25, 1.5)
        lp_hata = hata_urbano(800, 1.0, 25, 1.5)
        assert abs(lp_auto - lp_hata) < 1e-10

    def test_usa_cost231_para_1800mhz(self):
        """perdida_trayecto con 1800 MHz debe coincidir con cost231_hata."""
        lp_auto = perdida_trayecto(1800, 1.0, 25, 1.5)
        lp_c231 = cost231_hata(1800, 1.0, 25, 1.5, "urbano")
        assert abs(lp_auto - lp_c231) < 1e-10

    def test_800mhz_menor_perdida_que_1800mhz(self):
        """800 MHz debe presentar menor pérdida de trayecto que 1800 MHz."""
        lp_800 = perdida_trayecto(800, 2.0, 25, 1.5)
        lp_1800 = perdida_trayecto(1800, 2.0, 25, 1.5)
        assert lp_800 < lp_1800


# ---------------------------------------------------------------------------
# Link budget y RSRP
# ---------------------------------------------------------------------------


class TestEirp:
    def test_eirp_calculo(self):
        """EIRP = Potencia_tx + Ganancia_antena - Perdidas_cable."""
        lb = {"potencia_tx_dbm": 43, "ganancia_antena_bs_dbi": 17, "perdidas_cable_db": 2}
        assert eirp_dbm(lb) == 58.0

    def test_eirp_positivo(self):
        """EIRP del link budget del escenario debe ser positivo."""
        assert eirp_dbm(LINK_BUDGET) > 0


class TestRsrp:
    def test_rsrp_decrece_con_distancia(self):
        """RSRP debe disminuir al aumentar la distancia."""
        r1 = rsrp_dbm(800, 0.5, SCENARIO, LINK_BUDGET, False)
        r2 = rsrp_dbm(800, 2.0, SCENARIO, LINK_BUDGET, False)
        assert r2 < r1

    def test_rsrp_interior_menor_que_exterior(self):
        """RSRP interior debe ser menor que exterior (pérdidas de penetración)."""
        r_ext = rsrp_dbm(800, 1.0, SCENARIO, LINK_BUDGET, False)
        r_int = rsrp_dbm(800, 1.0, SCENARIO, LINK_BUDGET, True)
        assert r_int < r_ext
        assert abs(r_ext - r_int - LINK_BUDGET["perdidas_penetracion_db"]) < 1e-8

    def test_rsrp_800mhz_mayor_que_1800mhz(self):
        """A igual distancia, 800 MHz debe ofrecer mayor RSRP que 1800 MHz."""
        r_800 = rsrp_dbm(800, 2.0, SCENARIO, LINK_BUDGET, True)
        r_1800 = rsrp_dbm(1800, 2.0, SCENARIO, LINK_BUDGET, True)
        assert r_800 > r_1800


# ---------------------------------------------------------------------------
# Radio de cobertura
# ---------------------------------------------------------------------------


class TestRadioCobertura:
    def test_radio_800mhz_mayor_que_1800mhz(self):
        """800 MHz debe tener mayor radio de cobertura que 1800 MHz."""
        r_800 = radio_cobertura_km(800, QOS_THRESHOLDS["aceptable"], SCENARIO, LINK_BUDGET, True)
        r_1800 = radio_cobertura_km(1800, QOS_THRESHOLDS["aceptable"], SCENARIO, LINK_BUDGET, True)
        assert r_800 > r_1800

    def test_radio_exterior_mayor_que_interior(self):
        """El radio exterior debe ser mayor que el interior para la misma banda."""
        r_ext = radio_cobertura_km(800, QOS_THRESHOLDS["aceptable"], SCENARIO, LINK_BUDGET, False)
        r_int = radio_cobertura_km(800, QOS_THRESHOLDS["aceptable"], SCENARIO, LINK_BUDGET, True)
        assert r_ext > r_int

    def test_radio_disminuye_con_umbral_mas_estricto(self):
        """Un umbral más estricto (mayor RSRP) debe reducir el radio de cobertura."""
        r_acept = radio_cobertura_km(800, QOS_THRESHOLDS["aceptable"], SCENARIO, LINK_BUDGET, True)
        r_excel = radio_cobertura_km(800, QOS_THRESHOLDS["excelente"], SCENARIO, LINK_BUDGET, True)
        assert r_acept > r_excel

    def test_radio_positivo(self):
        """El radio de cobertura debe ser positivo para el umbral mínimo."""
        r = radio_cobertura_km(800, QOS_THRESHOLDS["sin_servicio"], SCENARIO, LINK_BUDGET, True)
        assert r > 0

    def test_radio_cero_si_no_cubre(self):
        """Si el umbral es muy alto (inalcanzable), el radio debe ser 0."""
        r = radio_cobertura_km(
            800, 0.0, SCENARIO, LINK_BUDGET, True, d_min=0.05, d_max=20.0
        )
        assert r == 0.0


# ---------------------------------------------------------------------------
# Tabla resumen
# ---------------------------------------------------------------------------


class TestTablaResumen:
    def test_tabla_tiene_filas(self):
        """La tabla debe contener filas para cada banda y umbral."""
        tabla = calcular_tabla_resumen(SCENARIO, LINK_BUDGET)
        n_bandas = len(BANDS)
        n_umbrales = len(QOS_THRESHOLDS)
        assert len(tabla) == n_bandas * n_umbrales

    def test_columnas_esperadas(self):
        """La tabla debe tener todas las columnas esperadas."""
        tabla = calcular_tabla_resumen(SCENARIO, LINK_BUDGET)
        columnas_esperadas = {
            "Banda",
            "Umbral",
            "RSRP (dBm)",
            "Radio exterior (km)",
            "Área exterior (km²)",
            "Radio interior (km)",
            "Área interior (km²)",
        }
        assert columnas_esperadas.issubset(set(tabla.columns))

    def test_radios_no_negativos(self):
        """Todos los radios en la tabla deben ser no negativos."""
        tabla = calcular_tabla_resumen(SCENARIO, LINK_BUDGET)
        assert (tabla["Radio exterior (km)"] >= 0).all()
        assert (tabla["Radio interior (km)"] >= 0).all()

    def test_area_coherente_con_radio(self):
        """Área ≈ π·r² para todos los registros (tolerancia de redondeo a 3 decimales)."""
        tabla = calcular_tabla_resumen(SCENARIO, LINK_BUDGET)
        for _, row in tabla.iterrows():
            area_calculada = math.pi * row["Radio exterior (km)"] ** 2
            # La tabla redondea a 3 decimales; se admite ±0.05 km² de tolerancia
            assert abs(row["Área exterior (km²)"] - area_calculada) < 0.05
