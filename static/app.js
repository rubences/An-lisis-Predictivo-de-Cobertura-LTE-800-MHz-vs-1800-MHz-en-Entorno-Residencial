const map = L.map("map").setView([40.4916, -3.7212], 15);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 20,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const latInput = document.getElementById("lat");
const lonInput = document.getElementById("lon");
const lat2Input = document.getElementById("lat2");
const lon2Input = document.getElementById("lon2");
const frequencyInput = document.getElementById("frequency");
const radiusInput = document.getElementById("radius");
const outputModeInput = document.getElementById("outputMode");
const dualModeCheckbox = document.getElementById("dualMode");
const dualControls = document.getElementById("dualControls");
const enableLOSCheckbox = document.getElementById("enableLOS");
const attenuationWallInput = document.getElementById("attenuationWall");
const visualizationModeInput = document.getElementById("visualizationMode");
const runButton = document.getElementById("runSimulation");
const statusBox = document.getElementById("status");
const summaryBox = document.getElementById("summary");
const chartCanvas = document.getElementById("coverageChart");
const chartSummary = document.getElementById("chartSummary");
const rasterContainer = document.getElementById("rasterContainer");
const rasterImage = document.getElementById("rasterImage");

let marker1 = null;
let marker2 = null;
let coverageLayer = null;
let hexLayer = null;
let coverageChart = null;

function colorForCoverage(covered) {
  return covered ? "#1a9850" : "#d73027";
}

function getServerColor(server) {
  return server === "1" ? "#0066cc" : "#ff6600";
}

function rsrpToColor(rsrp) {
  if (rsrp >= -80) return "#1a9850";      // Verde oscuro - excelente
  if (rsrp >= -90) return "#66bb6a";      // Verde claro - muy buena
  if (rsrp >= -100) return "#ffd166";     // Amarillo - aceptable
  if (rsrp >= -110) return "#f97316";     // Naranja - pobre
  return "#8b0000";                        // Rojo oscuro - sin servicio
}

function classifyCoverageBucket(rsrp) {
  if (rsrp >= -90) return "excellent";
  if (rsrp >= -105) return "acceptable";
  return "noCoverage";
}

function computeCoverageStats(features) {
  const stats = {
    excellent: 0,
    acceptable: 0,
    noCoverage: 0,
    total: 0,
  };

  if (!features || !Array.isArray(features)) {
    return stats;
  }

  features.forEach((feature) => {
    const rsrp = feature?.properties?.rsrp_dbm;
    if (typeof rsrp !== "number" || Number.isNaN(rsrp)) {
      return;
    }

    const bucket = classifyCoverageBucket(rsrp);
    stats[bucket] += 1;
    stats.total += 1;
  });

  return stats;
}

function updateCoverageChart(stats, sourceLabel) {
  if (!chartCanvas || !stats || stats.total === 0) {
    if (chartSummary) {
      chartSummary.textContent = "No hay datos suficientes para estadísticas.";
    }
    if (coverageChart) {
      coverageChart.destroy();
      coverageChart = null;
    }
    return;
  }

  const excellentPct = ((stats.excellent / stats.total) * 100).toFixed(1);
  const acceptablePct = ((stats.acceptable / stats.total) * 100).toFixed(1);
  const noCoveragePct = ((stats.noCoverage / stats.total) * 100).toFixed(1);

  const data = [stats.excellent, stats.acceptable, stats.noCoverage];

  if (coverageChart) {
    coverageChart.data.datasets[0].data = data;
    coverageChart.update();
  } else {
    const context = chartCanvas.getContext("2d");
    coverageChart = new Chart(context, {
      type: "doughnut",
      data: {
        labels: ["Excelente", "Aceptable", "Sin cobertura"],
        datasets: [
          {
            data,
            backgroundColor: ["#1a9850", "#ffd166", "#8b0000"],
            borderWidth: 1,
            borderColor: "#ffffff",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              boxWidth: 10,
              font: { size: 11 },
            },
          },
        },
      },
    });
  }

  if (chartSummary) {
    chartSummary.innerHTML =
      `Base: ${sourceLabel}<br>` +
      `Excelente: ${excellentPct}% · Aceptable: ${acceptablePct}% · Sin cobertura: ${noCoveragePct}%`;
  }
}

function createHexBinnedLayer(geoJsonData, bounds) {
  if (!geoJsonData || !geoJsonData.features || geoJsonData.features.length === 0) {
    return null;
  }

  try {
    const points = [];
    geoJsonData.features.forEach(feature => {
      const coord = feature.geometry.coordinates;
      const props = feature.properties;
      points.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: coord },
        properties: {
          rsrp_dbm: props.rsrp_dbm,
          server: props.server || "1",
          is_indoor: props.is_indoor || false
        }
      });
    });

    const pointsFeatureCollection = {
      type: "FeatureCollection",
      features: points
    };

    const [minLon, minLat, maxLon, maxLat] = bounds;
    const cellSize = 0.05;
    
    const hexGrid = turf.hexGrid([minLon, minLat, maxLon, maxLat], cellSize);

    hexGrid.features.forEach(hex => {
      const hexCenter = turf.centroid(hex);
      let sumRsrp = 0;
      let sumWeights = 0;
      let countServer1 = 0;
      let countServer2 = 0;

      const centerCoord = hexCenter.geometry.coordinates;

      points.forEach(point => {
        const pointCoord = point.geometry.coordinates;
        const distance = turf.distance(centerCoord, pointCoord, { units: "kilometers" });
        
        if (distance < 0.01) {
          sumRsrp += point.properties.rsrp_dbm;
          sumWeights += 1000;
          if (point.properties.server === "1") countServer1++;
          else countServer2++;
        } else {
          const weight = 1 / (distance * distance);
          sumRsrp += point.properties.rsrp_dbm * weight;
          sumWeights += weight;
          if (point.properties.server === "1") countServer1++;
          else countServer2++;
        }
      });

      const interpolatedRsrp = sumWeights > 0 ? sumRsrp / sumWeights : -120;
      const dominantServer = countServer1 >= countServer2 ? "1" : "2";

      hex.properties = {
        rsrp_dbm: Math.round(interpolatedRsrp * 10) / 10,
        server: dominantServer,
        pointCount: countServer1 + countServer2
      };
    });

    const hexGeoJSON = L.geoJSON(hexGrid, {
      style: (feature) => {
        const rsrp = feature.properties.rsrp_dbm;
        const color = rsrpToColor(rsrp);
        
        return {
          fillColor: color,
          weight: 1,
          opacity: 0.7,
          color: "#333",
          fillOpacity: 0.65
        };
      },
      onEachFeature: (feature, layer) => {
        const props = feature.properties;
        layer.bindPopup(
          `RSRP (interpolado): ${props.rsrp_dbm} dBm<br>` +
          `Mejor servidor: eNodeB ${props.server}<br>` +
          `Puntos en celda: ${props.pointCount}`
        );
      }
    });

    hexGeoJSON.hexGridData = hexGrid;
    return hexGeoJSON;
  } catch (error) {
    console.error("Error en hex binning:", error);
    return null;
  }
}

map.on("click", (event) => {
  const { lat, lng } = event.latlng;
  
  if (event.originalEvent.ctrlKey && dualModeCheckbox.checked) {
    lat2Input.value = lat.toFixed(6);
    lon2Input.value = lng.toFixed(6);
    
    if (marker2) {
      marker2.setLatLng(event.latlng);
    } else {
      marker2 = L.marker(event.latlng, { title: "eNodeB 2" }).addTo(map);
    }
    statusBox.textContent = "eNodeB 2 capturado. Puedes ejecutar la simulación.";
  } else {
    latInput.value = lat.toFixed(6);
    lonInput.value = lng.toFixed(6);
    
    if (marker1) {
      marker1.setLatLng(event.latlng);
    } else {
      marker1 = L.marker(event.latlng, { title: "eNodeB 1" }).addTo(map);
    }
    statusBox.textContent = "eNodeB 1 capturado.";
    if (dualModeCheckbox.checked) {
      statusBox.textContent += " Ctrl+clic para eNodeB 2.";
    }
  }
});

dualModeCheckbox.addEventListener("change", () => {
  dualControls.style.display = dualModeCheckbox.checked ? "block" : "none";
  if (!dualModeCheckbox.checked && marker2) {
    map.removeLayer(marker2);
    marker2 = null;
    lat2Input.value = "";
    lon2Input.value = "";
  }
});

async function runSimulation() {
  if (!latInput.value || !lonInput.value) {
    statusBox.textContent = "Selecciona primero una coordenada haciendo clic en el mapa.";
    return;
  }

  if (dualModeCheckbox.checked && (!lat2Input.value || !lon2Input.value)) {
    statusBox.textContent = "Dual mode activado. Selecciona eNodeB 2 con Ctrl+clic.";
    return;
  }

  runButton.disabled = true;
  statusBox.textContent = "Ejecutando simulación...";
  summaryBox.textContent = "";
  if (chartSummary) {
    chartSummary.textContent = "Calculando estadísticas...";
  }
  rasterContainer.style.display = "none";

  try {
    const payload = {
      lat: Number(latInput.value),
      lon: Number(lonInput.value),
      lat2: dualModeCheckbox.checked ? Number(lat2Input.value) : null,
      lon2: dualModeCheckbox.checked ? Number(lon2Input.value) : null,
      frecuencia_mhz: Number(frequencyInput.value),
      radio_m: Number(radiusInput.value),
      umbral_dbm: -105,
      muestreo_m: 30,
      output_mode: outputModeInput.value,
      enable_los: enableLOSCheckbox.checked,
      atenuacion_muro_db: Number(attenuationWallInput.value),
    };

    const response = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "No se pudo ejecutar la simulación.");
    }

    if (coverageLayer) {
      map.removeLayer(coverageLayer);
    }

    if (data.raster_b64) {
      rasterImage.src = data.raster_b64;
      rasterContainer.style.display = "block";
      const dualLabel = dualModeCheckbox.checked ? " (Dual eNodeB)" : "";
      summaryBox.innerHTML = `
        <strong>Resultado (Raster)${dualLabel}:</strong><br>
        Puntos evaluados: ${data.summary.total_points}<br>
        Cobertura: ${data.summary.covered_points} (${data.summary.coverage_pct}%)<br>
        Interiores: ${data.summary.indoor_points}<br>
        Sin cobertura: ${data.summary.uncovered_points}
      `;
      updateCoverageChart(
        {
          excellent: 0,
          acceptable: data.summary.covered_points,
          noCoverage: data.summary.uncovered_points,
          total: data.summary.total_points,
        },
        "puntos raster"
      );
      statusBox.textContent = "Simulación completada (Raster).";      
    } else if (data.geojson) {
      let visualMode = visualizationModeInput.value;
      const dualLabel = dualModeCheckbox.checked ? " (Dual eNodeB)" : "";

      if (visualMode === "hex") {
        hexLayer = createHexBinnedLayer(data.geojson, data.geojson.bounds);
        if (hexLayer) {
          coverageLayer = hexLayer.addTo(map);
          map.fitBounds(hexLayer.getBounds(), { padding: [20, 20] });
          const hexStats = computeCoverageStats(hexLayer.hexGridData?.features || []);
          updateCoverageChart(hexStats, "hexágonos IDW");
          statusBox.textContent = "Simulación completada (Hex-Binning IDW).";
        } else {
          statusBox.textContent = "Error en interpolación hex binning, mostrando puntos.";
          visualMode = "points";
        }
      }

      if (visualMode === "points") {
        coverageLayer = L.geoJSON(data.geojson, {
          pointToLayer: (feature, latlng) => {
            const server = feature.properties.server || "1";
            return L.circleMarker(latlng, {
              radius: 4,
              color: dualModeCheckbox.checked ? getServerColor(server) : colorForCoverage(feature.properties.covered),
              fillColor: dualModeCheckbox.checked ? getServerColor(server) : colorForCoverage(feature.properties.covered),
              fillOpacity: 0.72,
              weight: 0.2,
            });
          },
          onEachFeature: (feature, layer) => {
            const props = feature.properties;
            const indoorLabel = props.is_indoor ? " (Interior)" : "";
            const serverLabel = dualModeCheckbox.checked ? `<br>Servidor: eNodeB ${props.server}` : "";
            const losLabel = props.num_buildings_los > 0 ? `<br>Edificios LOS: ${props.num_buildings_los}` : "";
            layer.bindPopup(
              `RSRP: ${props.rsrp_dbm} dBm<br>` +
              `Distancia: ${props.distancia_km} km<br>` +
              `Cobertura: ${props.covered ? "Sí" : "No"}${indoorLabel}${serverLabel}${losLabel}`
            );
          },
        }).addTo(map);

        map.fitBounds(coverageLayer.getBounds(), { padding: [20, 20] });
        const pointStats = computeCoverageStats(data.geojson.features || []);
        updateCoverageChart(pointStats, "puntos discretos");
        statusBox.textContent = "Simulación completada (Puntos).";
      }

      summaryBox.innerHTML = `
        <strong>Resultado${dualLabel}:</strong><br>
        Puntos evaluados: ${data.summary.total_points}<br>
        Cobertura: ${data.summary.covered_points} (${data.summary.coverage_pct}%)<br>
        Interiores: ${data.summary.indoor_points}<br>
        Sin cobertura: ${data.summary.uncovered_points}
      `;
    }
  } catch (error) {
    statusBox.textContent = `Error: ${error.message}`;
  } finally {
    runButton.disabled = false;
  }
}

runButton.addEventListener("click", runSimulation);