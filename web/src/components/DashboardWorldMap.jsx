import { useMemo, useState } from "react";

function buildEmbedUrl(latitude, longitude) {
  const delta = 0.035;
  return (
    "https://www.openstreetmap.org/export/embed.html?" +
    new URLSearchParams({
      bbox: [
        longitude - delta,
        latitude - delta * 0.72,
        longitude + delta,
        latitude + delta * 0.72,
      ].join(","),
      layer: "mapnik",
      marker: `${latitude},${longitude}`,
    }).toString()
  );
}

function buildStreetViewUrl(latitude, longitude) {
  return (
    "https://www.google.com/maps/@" +
    "?api=1&map_action=pano&viewpoint=" +
    encodeURIComponent(`${latitude},${longitude}`) +
    "&heading=0&pitch=0&fov=90"
  );
}

export default function DashboardWorldMap() {
  const [position, setPosition] = useState(null);
  const [accuracy, setAccuracy] = useState(null);
  const [status, setStatus] = useState("READY");

  const mapUrl = useMemo(
    () =>
      position
        ? buildEmbedUrl(position.latitude, position.longitude)
        : "https://www.openstreetmap.org/export/embed.html?bbox=32.80,-7.00,43.00,2.00&layer=mapnik",
    [position]
  );

  function locate() {
    if (!navigator.geolocation) {
      setStatus("NOT_SUPPORTED");
      return;
    }

    setStatus("REQUESTING...");
    navigator.geolocation.getCurrentPosition(
      current => {
        setPosition({
          latitude: current.coords.latitude,
          longitude: current.coords.longitude,
        });
        setAccuracy(current.coords.accuracy);
        setStatus("LOCATION VERIFIED");
      },
      error => {
        setStatus(error.code === error.PERMISSION_DENIED ? "PERMISSION DENIED" : "LOCATION ERROR");
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 30000,
      }
    );
  }

  return (
    <div className="world-map-widget">
      <div className="world-map-toolbar">
        <button className="hud-mini-button" onClick={locate}>LOCATE DEVICE</button>
        {position ? (
          <a
            className="hud-mini-button"
            href={buildStreetViewUrl(position.latitude, position.longitude)}
            target="_blank"
            rel="noreferrer"
          >
            STREET VIEW
          </a>
        ) : (
          <span className="map-state">{status}</span>
        )}
      </div>

      <div className="world-map-frame">
        <iframe
          title="MR AI STAN world map"
          src={mapUrl}
          loading="lazy"
          referrerPolicy="no-referrer-when-downgrade"
        />
      </div>

      <div className="world-map-readout">
        <div>
          <span>STATUS</span>
          <strong>{status}</strong>
        </div>
        <div>
          <span>LAT</span>
          <strong>{Number.isFinite(position?.latitude) ? position.latitude.toFixed(5) : "N/A"}</strong>
        </div>
        <div>
          <span>LON</span>
          <strong>{Number.isFinite(position?.longitude) ? position.longitude.toFixed(5) : "N/A"}</strong>
        </div>
        <div>
          <span>ACC</span>
          <strong>{Number.isFinite(accuracy) ? `${Math.round(accuracy)}m` : "N/A"}</strong>
        </div>
      </div>
    </div>
  );
}
