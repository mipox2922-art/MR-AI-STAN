import { useEffect, useMemo, useRef, useState } from "react";

const DEFAULT_CENTER = { lat: -6.7924, lng: 39.2083 };

function distanceMeters(a, b) {
  if (!a || !b) return Infinity;
  const rad = value => value * Math.PI / 180;
  const dLat = rad(b.lat - a.lat), dLng = rad(b.lng - a.lng);
  const lat1 = rad(a.lat), lat2 = rad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 6371000 * 2 * Math.asin(Math.min(1, Math.sqrt(h)));
}

function buildOpenStreetMapEmbedUrl(latitude, longitude) {
  const dx = 0.012, dy = 0.0085;
  return "https://www.openstreetmap.org/export/embed.html?" + new URLSearchParams({
    bbox: `${longitude - dx},${latitude - dy},${longitude + dx},${latitude + dy}`,
    layer: "mapnik",
    marker: `${latitude},${longitude}`,
  }).toString();
}

function buildStreetViewUrl(latitude, longitude, heading = 0) {
  return "https://www.google.com/maps/@" +
    "?api=1&map_action=pano&viewpoint=" + encodeURIComponent(`${latitude},${longitude}`) +
    `&heading=${Math.round(heading || 0)}&pitch=0&fov=90`;
}

export default function LiveMap({ onOpenMap, fullPage = false }) {
  const [center, setCenter] = useState(DEFAULT_CENTER);
  const [mapCenter, setMapCenter] = useState(DEFAULT_CENTER);
  const [accuracy, setAccuracy] = useState(null);
  const [speed, setSpeed] = useState(null);
  const [heading, setHeading] = useState(null);
  const [status, setStatus] = useState("PREVIEW · LOCATION NOT VERIFIED");
  const [tracking, setTracking] = useState(false);
  const [hasFix, setHasFix] = useState(false);
  const [lastFixAt, setLastFixAt] = useState(null);
  const watchIdRef = useRef(null);
  const mapCenterRef = useRef(DEFAULT_CENTER);
  const lastMapRefreshRef = useRef(0);

  const mapUrl = useMemo(() => buildOpenStreetMapEmbedUrl(mapCenter.lat, mapCenter.lng), [mapCenter.lat, mapCenter.lng]);
  const streetViewUrl = useMemo(() => buildStreetViewUrl(center.lat, center.lng, heading || 0), [center.lat, center.lng, heading]);

  function recenterMap(next) {
    mapCenterRef.current = next;
    lastMapRefreshRef.current = Date.now();
    setMapCenter(next);
  }

  function applyPosition(position, forceRecenter = false) {
    const next = { lat: position.coords.latitude, lng: position.coords.longitude };
    const now = Date.now();
    setCenter(next);
    setAccuracy(Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : null);
    setSpeed(Number.isFinite(position.coords.speed) && position.coords.speed >= 0 ? position.coords.speed : null);
    setHeading(Number.isFinite(position.coords.heading) ? position.coords.heading : null);
    setHasFix(true);
    setLastFixAt(now);
    // Follow movement without refreshing the map iframe on every GPS tick.
    if (forceRecenter || distanceMeters(mapCenterRef.current, next) >= 45 || now - lastMapRefreshRef.current >= 15000) {
      recenterMap(next);
    }
  }

  function locationError(error) {
    setTracking(false);
    setStatus(error?.code === error.PERMISSION_DENIED
      ? "LOCATION PERMISSION DENIED"
      : error?.code === error.TIMEOUT ? "GPS TIMEOUT · RETRY" : "LOCATION UNAVAILABLE");
    if (watchIdRef.current !== null) {
      navigator.geolocation?.clearWatch(watchIdRef.current);
      watchIdRef.current = null;
    }
  }

  function locateOnce() {
    if (!navigator.geolocation) { setStatus("GEOLOCATION NOT SUPPORTED"); return; }
    setStatus("REQUESTING LOCATION PERMISSION");
    navigator.geolocation.getCurrentPosition(position => {
      applyPosition(position, true);
      setStatus("LOCATION VERIFIED · FOLLOW OFF");
    }, locationError, { enableHighAccuracy: true, timeout: 15000, maximumAge: 5000 });
  }

  function startTracking() {
    if (!navigator.geolocation) { setStatus("GEOLOCATION NOT SUPPORTED"); return; }
    if (watchIdRef.current !== null) return;
    setTracking(true);
    setStatus("STARTING LIVE FOLLOW");
    watchIdRef.current = navigator.geolocation.watchPosition(position => {
      applyPosition(position);
      setStatus("LIVE TRACKING · FOLLOWING DEVICE");
    }, locationError, { enableHighAccuracy: true, timeout: 20000, maximumAge: 3000 });
  }

  function stopTracking() {
    if (watchIdRef.current !== null) {
      navigator.geolocation?.clearWatch(watchIdRef.current);
      watchIdRef.current = null;
    }
    setTracking(false);
    setStatus(hasFix ? "LOCATION VERIFIED · FOLLOW PAUSED" : "FOLLOW PAUSED · NO GPS FIX");
  }

  useEffect(() => () => {
    if (watchIdRef.current !== null) navigator.geolocation?.clearWatch(watchIdRef.current);
    watchIdRef.current = null;
  }, []);

  const freshness = lastFixAt
    ? `UPDATED ${new Date(lastFixAt).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`
    : "WAITING FOR GPS";

  return (
    <div className={`cc-live-map ${fullPage ? "cc-live-map-full-page" : ""}`}>
      {fullPage && <div className="cc-map-module-title">
        <div><span className="cc-eyebrow">MOG343 · LOCATION</span><h2>Live Tracking Map</h2></div>
        <span className={`cc-map-follow-pill ${tracking ? "is-following" : ""}`}>{tracking ? "● FOLLOW ACTIVE" : "○ FOLLOW OFF"}</span>
      </div>}
      <div className="cc-map-toolbar">
        <button type="button" className="cc-inline-button" onClick={locateOnce} disabled={tracking}>LOCATE ONCE</button>
        {!tracking
          ? <button type="button" className="cc-inline-button cc-map-track-button" onClick={startTracking}>▶ START LIVE TRACKING</button>
          : <button type="button" className="cc-inline-button cc-map-track-button is-following" onClick={stopTracking}>■ STOP TRACKING</button>}
        <a
          className={`cc-inline-button ${hasFix ? "" : "is-disabled"}`}
          href={hasFix ? streetViewUrl : undefined}
          aria-disabled={!hasFix}
          onClick={event => { if (!hasFix) event.preventDefault(); }}
          target="_blank"
          rel="noreferrer"
        >{hasFix ? "↗ OPEN STREET VIEW" : "⌖ STREET VIEW · GPS REQUIRED"}</a>
        {!fullPage && <button type="button" className="cc-inline-button" onClick={onOpenMap}>OPEN MAP MODULE</button>}
        <span className={`cc-map-state ${tracking ? "is-tracking" : ""}`}>{status}{accuracy != null ? ` · ±${Math.round(accuracy)}m` : ""}</span>
      </div>
      <div className="cc-map-frame-grid">
        <div className="cc-real-map">
          <div className="cc-map-frame-label">{hasFix ? "OPENSTREETMAP · LIVE 2D ROADMAP" : "OPENSTREETMAP · 2D MAP PREVIEW"}</div>
          <iframe className="cc-google-map-iframe" src={mapUrl} title="MR AI live OpenStreetMap tracking" loading="lazy" referrerPolicy="no-referrer-when-downgrade" />
          <a className="cc-map-attribution" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>
          {tracking && <span className="cc-map-live-indicator"><i /> LIVE FOLLOW</span>}
        </div>
        <div className="cc-street-view">
          <div className="cc-map-frame-label">STREET VIEW · CURRENT GPS</div>
          <div className="cc-street-view-scene">
            <div className="cc-street-view-target" aria-hidden="true">SV</div>
            <strong>{hasFix ? "GPS LOCK ACQUIRED" : "WAITING FOR GPS FIX"}</strong>
            <span className="cc-street-view-scene-caption">{hasFix ? "REAL STREET PANORAMA · EXTERNAL VIEWER" : "WAITING FOR VERIFIED GPS · EXTERNAL VIEWER"}</span>
          </div>
          <div className="cc-street-view-info">
            <strong>{hasFix ? `${center.lat.toFixed(5)}, ${center.lng.toFixed(5)}` : "Awaiting location permission"}</strong>
            <span>{hasFix ? "Open the closest available panorama for this GPS fix." : "This styled panel is a preview, not camera imagery. Open a real panorama below."}</span>
          </div>
          <a
            className={`cc-street-view-open ${hasFix ? "" : "is-disabled"}`}
            href={hasFix ? streetViewUrl : undefined}
            aria-disabled={!hasFix}
            onClick={event => { if (!hasFix) event.preventDefault(); }}
            target="_blank"
            rel="noreferrer"
          ><span>↗</span><strong>{hasFix ? "VIEW REAL STREET PANORAMA" : "WAITING FOR VERIFIED GPS"}</strong></a>
        </div>
      </div>
      <div className="cc-map-readout">
        <div><span>LOCATION</span><strong>{hasFix ? "GPS VERIFIED" : "PREVIEW ONLY"}</strong></div>
        <div><span>LATITUDE</span><strong>{hasFix ? center.lat.toFixed(5) : "N/A"}</strong></div>
        <div><span>LONGITUDE</span><strong>{hasFix ? center.lng.toFixed(5) : "N/A"}</strong></div>
        <div><span>SPEED</span><strong>{speed === null ? "N/A" : `${(speed * 3.6).toFixed(1)} km/h`}</strong></div>
        <div><span>HEADING</span><strong>{heading === null ? "N/A" : `${Math.round(heading)}°`}</strong></div>
        <div><span>LAST FIX</span><strong>{freshness}</strong></div>
      </div>
      <p className="cc-map-tracking-note">{tracking
        ? "MR AI is following the location reported by this browser. Allow precise location for continuous updates."
        : "The map preview is not your live location until you grant location permission and start tracking."} Street View opens a Google Maps panorama externally where coverage exists.</p>
    </div>
  );
}
