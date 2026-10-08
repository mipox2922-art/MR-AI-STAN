import { useEffect, useRef, useState } from "react";

const DEFAULT_CENTER = { lat: -6.7924, lng: 39.2083 };

function loadGoogleMaps(apiKey) {
  if (window.google?.maps) return Promise.resolve(window.google.maps);
  if (window.__mrAiGoogleMapsPromise) return window.__mrAiGoogleMapsPromise;

  window.__mrAiGoogleMapsPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-mr-ai-google-maps="true"]');
    if (existing) {
      existing.addEventListener("load", () => resolve(window.google.maps), { once: true });
      existing.addEventListener("error", reject, { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = "https://maps.googleapis.com/maps/api/js?key=" + encodeURIComponent(apiKey) + "&v=weekly";
    script.async = true;
    script.defer = true;
    script.dataset.mrAiGoogleMaps = "true";
    script.onload = () => resolve(window.google.maps);
    script.onerror = () => reject(new Error("Google Maps JavaScript API failed to load"));
    document.head.appendChild(script);
  });

  return window.__mrAiGoogleMapsPromise;
}

function streetViewFallbackUrl(center) {
  return "https://maps.google.com/maps?q=&layer=c&cbll=" +
    encodeURIComponent(center.lat + "," + center.lng) +
    "&cbp=11,0,0,0,0&output=svembed";
}

export default function LiveGoogleMap({ onOpenMap }) {
  const mapNode = useRef(null);
  const streetNode = useRef(null);
  const mapRef = useRef(null);
  const streetRef = useRef(null);
  const markerRef = useRef(null);
  const [center, setCenter] = useState(DEFAULT_CENTER);
  const [accuracy, setAccuracy] = useState(null);
  const [status, setStatus] = useState("DEFAULT VIEW");
  const [mapReady, setMapReady] = useState(false);
  const apiKey = String(import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "").trim();

  useEffect(() => {
    if (!apiKey) {
      setMapReady(false);
      return undefined;
    }

    let disposed = false;
    loadGoogleMaps(apiKey)
      .then(maps => {
        if (disposed || !mapNode.current) return;
        const map = new maps.Map(mapNode.current, {
          center,
          zoom: 12,
          mapTypeId: "roadmap",
          tilt: 0,
          heading: 0,
          fullscreenControl: true,
          mapTypeControl: false,
          streetViewControl: false,
          rotateControl: false,
          scaleControl: true,
          zoomControl: true,
          gestureHandling: "greedy",
        });
        const street = streetNode.current
          ? new maps.StreetViewPanorama(streetNode.current, {
              position: center,
              pov: { heading: 0, pitch: 0 },
              zoom: 1,
              addressControl: true,
              linksControl: true,
              panControl: true,
              motionTracking: false,
              fullscreenControl: true,
              enableCloseButton: false,
            })
          : null;
        mapRef.current = map;
        streetRef.current = street;
        markerRef.current = new maps.Marker({
          position: center,
          map,
          title: "MR AI reference point",
          label: "MR",
        });
        setMapReady(true);
      })
      .catch(() => {
        if (!disposed) {
          setMapReady(false);
          setStatus("MAP API UNAVAILABLE");
        }
      });

    return () => {
      disposed = true;
      if (markerRef.current) markerRef.current.setMap(null);
      mapRef.current = null;
      streetRef.current = null;
      markerRef.current = null;
    };
  }, [apiKey]);

  useEffect(() => {
    if (!mapReady) return;
    mapRef.current?.setCenter(center);
    mapRef.current?.setZoom(12);
    markerRef.current?.setPosition(center);
    streetRef.current?.setPosition(center);
  }, [center, mapReady]);

  function locateDevice() {
    if (!navigator.geolocation) {
      setStatus("GEOLOCATION NOT SUPPORTED");
      return;
    }
    setStatus("REQUESTING LOCATION...");
    navigator.geolocation.getCurrentPosition(
      position => {
        setCenter({ lat: position.coords.latitude, lng: position.coords.longitude });
        setAccuracy(position.coords.accuracy);
        setStatus("LOCATION VERIFIED");
      },
      error => {
        setStatus(error.code === error.PERMISSION_DENIED ? "LOCATION PERMISSION DENIED" : "LOCATION UNAVAILABLE");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
    );
  }

  const fallbackMapUrl = "https://www.google.com/maps?q=" +
    encodeURIComponent(center.lat + "," + center.lng) + "&z=12&output=embed";

  return (
    <div className="cc-live-map">
      <div className="cc-map-toolbar">
        <button className="cc-inline-button" onClick={locateDevice}>LOCATE DEVICE</button>
        <button className="cc-inline-button" onClick={onOpenMap}>OPEN MAP MODULE</button>
        <span className="cc-map-state">{status}{accuracy != null ? " · ±" + Math.round(accuracy) + "m" : ""}</span>
      </div>
      <div className="cc-map-frame-grid">
        <div className="cc-real-map">
          <div className="cc-map-frame-label">GOOGLE MAPS · 2D ROADMAP</div>
          {apiKey ? (
            <div ref={mapNode} className="cc-google-map-canvas" aria-label="Live Google map" />
          ) : (
            <iframe className="cc-google-map-iframe" src={fallbackMapUrl} title="Google Maps" loading="lazy" referrerPolicy="no-referrer-when-downgrade" />
          )}
          {!apiKey && <div className="cc-map-api-note">GOOGLE MAPS API KEY NOT CONFIGURED · FALLBACK EMBED ACTIVE</div>}
        </div>
        <div className="cc-street-view">
          <div className="cc-map-frame-label">STREET VIEW</div>
          {apiKey ? (
            <div ref={streetNode} className="cc-street-view-canvas" aria-label="Google Street View" />
          ) : (
            <iframe className="cc-street-view-iframe" src={streetViewFallbackUrl(center)} title="Google Street View" loading="lazy" referrerPolicy="no-referrer-when-downgrade" />
          )}
        </div>
      </div>
      <div className="cc-map-readout">
        <div><span>VIEW</span><strong>2D MAP</strong></div>
        <div><span>LAT</span><strong>{center.lat.toFixed(4)}</strong></div>
        <div><span>LON</span><strong>{center.lng.toFixed(4)}</strong></div>
      </div>
    </div>
  );
}
