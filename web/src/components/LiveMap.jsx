import { useMemo, useState } from "react";

const DEFAULT_CENTER = { lat: -6.7924, lng: 39.2083 };

function buildOpenStreetMapEmbedUrl(latitude, longitude) {
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

function buildStreetViewUrl(latitude, longitude) {
  return (
    "https://www.google.com/maps/@" +
    "?api=1&map_action=pano&viewpoint=" +
    encodeURIComponent(`${latitude},${longitude}`) +
    "&heading=0&pitch=0&fov=90"
  );
}

export default function LiveMap({ onOpenMap }) {
  const [center, setCenter] = useState(DEFAULT_CENTER);
  const [accuracy, setAccuracy] = useState(null);
  const [status, setStatus] = useState("DEFAULT VIEW");

  const mapUrl = useMemo(
    () => buildOpenStreetMapEmbedUrl(center.lat, center.lng),
    [center.lat, center.lng]
  );

  const streetViewUrl = useMemo(
    () => buildStreetViewUrl(center.lat, center.lng),
    [center.lat, center.lng]
  );

  function locateDevice() {
    if (!navigator.geolocation) {
      setStatus("GEOLOCATION NOT SUPPORTED");
      return;
    }

    setStatus("REQUESTING LOCATION...");
    navigator.geolocation.getCurrentPosition(
      position => {
        setCenter({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        });
        setAccuracy(position.coords.accuracy);
        setStatus("LOCATION VERIFIED");
      },
      error => {
        setStatus(
          error.code === error.PERMISSION_DENIED
            ? "LOCATION PERMISSION DENIED"
            : "LOCATION UNAVAILABLE"
        );
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 30000,
      }
    );
  }

  return (
    <div className="cc-live-map">
      <div className="cc-map-toolbar">
        <button className="cc-inline-button" onClick={locateDevice}>
          LOCATE DEVICE
        </button>

        <a
          className="cc-inline-button"
          href={streetViewUrl}
          target="_blank"
          rel="noreferrer"
        >
          STREET VIEW
        </a>

        <button className="cc-inline-button" onClick={onOpenMap}>
          OPEN MAP MODULE
        </button>

        <span className="cc-map-state">
          {status}
          {accuracy != null ? ` · ±${Math.round(accuracy)}m` : ""}
        </span>
      </div>

      <div className="cc-map-frame-grid">
        <div className="cc-real-map">
          <div className="cc-map-frame-label">
            OPENSTREETMAP · 2D ROADMAP
          </div>

          <iframe
            className="cc-google-map-iframe"
            src={mapUrl}
            title="MR AI live OpenStreetMap"
            loading="lazy"
            referrerPolicy="no-referrer-when-downgrade"
          />

          <a
            className="cc-map-attribution"
            href="https://www.openstreetmap.org/copyright"
            target="_blank"
            rel="noreferrer"
          >
            © OpenStreetMap contributors
          </a>
        </div>

        <div className="cc-street-view">
          <div className="cc-map-frame-label">STREET VIEW</div>

          <button
            className="cc-street-view-launch"
            onClick={() => window.open(streetViewUrl, "_blank", "noopener,noreferrer")}
          >
            <span>↗</span>
            <strong>OPEN STREET VIEW</strong>
            <small>Google Street View · external viewer</small>
          </button>
        </div>
      </div>

      <div className="cc-map-readout">
        <div>
          <span>VIEW</span>
          <strong>2D MAP</strong>
        </div>
        <div>
          <span>LAT</span>
          <strong>{center.lat.toFixed(4)}</strong>
        </div>
        <div>
          <span>LON</span>
          <strong>{center.lng.toFixed(4)}</strong>
        </div>
      </div>
    </div>
  );
}
