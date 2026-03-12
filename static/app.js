const map = L.map("map").setView([40.4916, -3.7212], 15);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 20,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const latInput = document.getElementById("lat");
const lonInput = document.getElementById("lon");
const frequencyInput = document.getElementById("frequency");
const radiusInput = document.getElementById("radius");
const runButton = document.getElementById("runSimulation");
const statusBox = document.getElementById("status");
const summaryBox = document.getElementById("summary");

let selectedMarker = null;
let coverageLayer = null;

function colorForCoverage(covered) {
  return covered ? "#1a9850" : "#d73027";
}

map.on("click", (event) => {
  const { lat, lng } = event.latlng;
  latInput.value = lat.toFixed(6);
  lonInput.value = lng.toFixed(6);

  if (selectedMarker) {
    selectedMarker.setLatLng(event.latlng);
  } else {
    selectedMarker = L.marker(event.latlng).addTo(map);
  }

  statusBox.textContent = "Coordenadas capturadas. Puedes ejecutar la simulación.";
});

async function runSimulation() {
  if (!latInput.value || !lonInput.value) {
    statusBox.textContent = "Selecciona primero una coordenada haciendo clic en el mapa.";
    return;
  }

  runButton.disabled = true;
  statusBox.textContent = "Ejecutando simulación...";
  summaryBox.textContent = "";

  try {
    const payload = {
      lat: Number(latInput.value),
      lon: Number(lonInput.value),
      frecuencia_mhz: Number(frequencyInput.value),
      radio_m: Number(radiusInput.value),
      umbral_dbm: -105,
      muestreo_m: 30,
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

    coverageLayer = L.geoJSON(data.geojson, {
      pointToLayer: (feature, latlng) =>
        L.circleMarker(latlng, {
          radius: 4,
          color: colorForCoverage(feature.properties.covered),
          fillColor: colorForCoverage(feature.properties.covered),
          fillOpacity: 0.72,
          weight: 0.2,
        }),
      onEachFeature: (feature, layer) => {
        const props = feature.properties;
        layer.bindPopup(
          `RSRP: ${props.rsrp_dbm} dBm<br>` +
          `Distancia: ${props.distancia_km} km<br>` +
          `Cobertura: ${props.covered ? "Sí" : "No"}`
        );
      },
    }).addTo(map);

    map.fitBounds(coverageLayer.getBounds(), { padding: [20, 20] });

    summaryBox.innerHTML = `
      <strong>Resultado:</strong><br>
      Puntos evaluados: ${data.summary.total_points}<br>
      Cobertura: ${data.summary.covered_points} (${data.summary.coverage_pct}%)<br>
      Sin cobertura: ${data.summary.uncovered_points}
    `;
    statusBox.textContent = "Simulación completada.";
  } catch (error) {
    statusBox.textContent = `Error: ${error.message}`;
  } finally {
    runButton.disabled = false;
  }
}

runButton.addEventListener("click", runSimulation);