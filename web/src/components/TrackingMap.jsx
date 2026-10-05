import { useMemo, useState } from "react";

function buildEmbedUrl(latitude, longitude) {
  const delta = 0.035;
  const left = longitude - delta;
  const right = longitude + delta;
  const bottom = latitude - delta * 0.72;
  const top = latitude + delta * 0.72;
  return (
    "https://www.openstreetmap.org/export/embed.html?" +
    new URLSearchParams({
      bbox: `${left},${bottom},${right},${top}`,
      layer: "mapnik",
      marker: `${latitude},${longitude}`,
    }).toString()
  );
}

function formatCoordinate(value, digits = 5) {
  return Number.isFinite(value) ? value.toFixed(digits) : "N/A";
}

export default function TrackingMap() {
  const [position, setPosition] = useState(null);
  const [status, setStatus] = useState("READY");
  const [accuracy, setAccuracy] = useState(null);

  function locateMe() {
    if (!("geolocation" in navigator)) {
      setStatus("NOT_SUPPORTED");
      return;
    }

    setStatus("REQUESTING_PERMISSION");
    navigator.geolocation.getCurrentPosition(
      current => {
        setPosition({
          latitude: current.coords.latitude,
          longitude: current.coords.longitude,
        });
        setAccuracy(current.coords.accuracy);
        setStatus("LOCATION_VERIFIED");
      },
      error => {
        setStatus(
          error.code === error.PERMISSION_DENIED
            ? "PERMISSION_DENIED"
            : "LOCATION_ERROR"
        );
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 30000,
      }
    );
  }

  const mapUrl = useMemo(
    () =>
      position
        ? buildEmbedUrl(position.latitude, position.longitude)
        : "https://www.openstreetmap.org/export/embed.html?bbox=32.80,-7.00,43.00,2.00&layer=mapnik",
    [position]
  );

  return (
    <section className="panel large-panel map-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">LOCATION MAP</span>
          <h2>Authorized Tracking Map</h2>
        </div>
        <span className={`badge ${status === "LOCATION_VERIFIED" ? "badge-live" : ""}`}>
          {status}
        </span>
      </div>

      <div className="map-toolbar">
        <button className="primary-button" onClick={locateMe}>
          LOCATE MY DEVICE
        </button>
        <div className="map-coords">
          <span>
            LAT <strong>{formatCoordinate(position?.latitude)}</strong>
          </span>
          <span>
            LON <strong>{formatCoordinate(position?.longitude)}</strong>
          </span>
          <span>
            ACC <strong>{Number.isFinite(accuracy) ? Math.round(accuracy) + "m" : "N/A"}</strong>
          </span>
        </div>
      </div>

      <div className="map-frame">
        <iframe
          title="MR AI STAN OpenStreetMap tracking map"
          src={mapUrl}
          loading="lazy"
          referrerPolicy="no-referrer-when-downgrade"
        />
      </div>

      <div className="map-foot">
        <span>
          Map data © OpenStreetMap contributors. Location appears only after the
          operator grants browser location permission.
        </span>
        <span>
          Gmail activity can provide recent account IPs and approximate locations
          in Google’s own activity view; MR AI does not invent GPS coordinates from an IP.
        </span>
      </div>
    </section>
  );
}
