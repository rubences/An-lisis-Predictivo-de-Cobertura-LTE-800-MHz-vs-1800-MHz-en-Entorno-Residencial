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
const runButton = document.getElementById("runSimulation");
const statusBox = document.getElementById("status");
const summaryBox = document.getElementById("summary");
const rasterContainer = document.getElementById("rasterContainer");
const rasterImage = document.getElementById("rasterImage");

let marker1 = null;
let marker2 = null;
let coverageLayer = null;

function colorForCoverage(covered) {
  return covered ? "#1a9850" : "#d73027";
}

function getServerColor(server) {
  return server === "1" ? "#0066cc" : "#ff6600";
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
      statusBox.textContent = "Simulación completada (Raster).";      
    } else if (data.geojson) {
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

      const dualLabel = dualModeCheckbox.checked ? " (Dual eNodeB)" : "";
      summaryBox.innerHTML = `
        <strong>Resultado (Puntos)${dualLabel}:</strong><br>
        Puntos evaluados: ${data.summary.total_points}<br>
        Cobertura: ${data.summary.covered_points} (${data.summary.coverage_pct}%)<br>
        Interiores: ${data.summary.indoor_points}<br>
        Sin cobertura: ${data.summary.uncovered_points}
      `;
      statusBox.textContent = "Simulación completada (Puntos).";      
    }
  } catch (error) {
    statusBox.textContent = `Error: ${error.message}`;
  } finally {
    runButton.disabled = false;
  }
}

runButton.addEventListener("click", runSimulation);