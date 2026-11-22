const map = new L.LeafletMap("map", { zoomControl: false });
new L.ZoomControl({ position: "bottomright" }).addTo(map);

map.setView([9.74, 118.74], 11);

const tiles = new L.TileLayer(
  "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  },
);

tiles.addTo(map);

const mapTools = document.getElementById("mapTools");

L.DomEvent.disableClickPropagation(mapTools);
L.DomEvent.disableScrollPropagation(mapTools);

// Prevent clicks on controls from reaching the map
mapTools.addEventListener("click", function (e) {
  e.stopPropagation();
});

mapTools.addEventListener("dblclick", function (e) {
  e.stopPropagation();
});

const searchInput = document.getElementById("placeSearch");
const searchBtn = document.getElementById("searchBtn");
const searchResults = document.getElementById("searchResults");

const searchMarkers = [];

searchBtn.addEventListener("click", searchPlace);

searchInput.addEventListener("keydown", function (e) {
  if (e.key === "Enter") {
    searchPlace();
  }
});

async function searchPlace() {
  const query = searchInput.value.trim();

  if (query === "") {
    alert("Please enter a place name.");
    return;
  }

  searchResults.innerHTML = "Searching...";

  try {
    const params = new URLSearchParams({
      q: query,
      format: "jsonv2",
      limit: "5",
      countrycodes: "ph",
    });

    const url =
      "https://nominatim.openstreetmap.org/search?" + params.toString();

    const response = await fetch(url);

    if (!response.ok) {
      throw new Error("Search request failed.");
    }

    const places = await response.json();

    searchResults.innerHTML = "";

    if (places.length === 0) {
      searchResults.textContent = "No places found.";
      return;
    }

    places.forEach(function (place) {
      const resultButton = document.createElement("button");

      resultButton.className = "search-result";

      resultButton.textContent = place.display_name;

      resultButton.addEventListener("click", function () {
        const lat = Number(place.lat);
        const lng = Number(place.lon);

        map.setView([lat, lng], 16);

        const marker = new L.Marker([lat, lng]).addTo(map);

        marker
          .bindPopup("<b>" + escapeHTML(place.display_name) + "</b>")
          .openPopup();

        searchMarkers.push(marker);
      });

      searchResults.appendChild(resultButton);
    });
  } catch (error) {
    searchResults.textContent = "Unable to search. Please try again.";

    console.error(error);
  }
}

function escapeHTML(text) {
  const element = document.createElement("div");

  element.textContent = text;

  return element.innerHTML;
}

const locationMarker = new L.Marker([0, 0]).addTo(map);

const locationArea = new L.Circle([0, 0]).addTo(map);

map.locate({
  setView: true,
  maxZoom: 16,
  watch: true,
  enableHighAccuracy: true,
});

map.on("locationfound", function (e) {
  locationMarker.setLatLng(e.latlng);

  locationMarker.bindPopup("Your current location").openPopup();
});

map.on("locationfound", function (e) {
  locationArea.setLatLng(e.latlng);
});

map.on("locationerror", function (e) {
  alert("Unable to get your location: " + e.message);
});

const addMarkerBtn = document.getElementById("addMarkerBtn");

let markers = JSON.parse(localStorage.getItem("leafletMarkers") || "[]");

let addingMarker = false;

function saveMarkers() {
  localStorage.setItem("leafletMarkers", JSON.stringify(markers));
}

function displayMarker(data) {
  const marker = new L.Marker([data.lat, data.lng]).addTo(map);

  const popupContent = document.createElement("div");

  const message = document.createElement("p");
  message.textContent = data.message;

  const deleteButton = document.createElement("button");
  deleteButton.textContent = "Remove Marker";

  popupContent.appendChild(message);
  popupContent.appendChild(deleteButton);

  marker.bindPopup(popupContent);

  deleteButton.addEventListener("click", function () {

    map.removeLayer(marker);

    markers = markers.filter(function (item) {
      return item.id !== data.id;
    });

    saveMarkers();
  });

  return marker;
}

markers.forEach(function (data) {
  displayMarker(data);
});

addMarkerBtn.addEventListener("click", function () {
  addingMarker = !addingMarker;

  if (addingMarker) {
    addMarkerBtn.textContent = "Click Map to Add";
  } else {
    addMarkerBtn.textContent = "Add Marker";
  }
});

map.on("click", function (e) {
  if (!addingMarker) {
    return;
  }

  const message = prompt("Enter a message:");

  if (message === null || message.trim() === "") {
    return;
  }

  const newMarker = {
    id: Date.now().toString(),
    lat: e.latlng.lat,
    lng: e.latlng.lng,
    message: message.trim(),
  };

  markers.push(newMarker);
  saveMarkers();

  displayMarker(newMarker);

  addingMarker = false;
  addMarkerBtn.textContent = "Add Marker";
});
