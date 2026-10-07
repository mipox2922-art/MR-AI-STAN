import { useState } from "react";
import {
  getDeviceBridgeHealth,
  getAndroidDevices,
  getFastbootDevices,
  scanBluetooth,
  getAndroidDeviceInfo,
  getAndroidDiagnostics,
  getBootState,
  scanWifi,
  rebootAndroid,
  setBridgeToken,
  getRadioStatus,
  scanRadar
} from "../api";

export default function DeviceLab() {
  const [token, setToken] = useState(localStorage.getItem("mr_ai_bridge_token") || "");
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState("");

  async function run(label, fn) {
    setResult({ label, status: "RUNNING" });
    try {
      const data = await fn();
      setResult({ label, status: "COMPLETED", data });
    } catch (error) {
      setResult({ label, status: "ERROR", error: error.message });
    }
  }

  function saveToken() {
    setBridgeToken(token.trim());
    setResult({ label: "BRIDGE TOKEN", status: "SAVED" });
  }

  return (
    <section className="tool-panel">
      <div className="panel-title">AUTHORIZED DEVICE LAB</div>
      <div className="tool-row">
        <input type="password" value={token} onChange={e => setToken(e.target.value)} placeholder="Local bridge token" />
        <button onClick={saveToken}>SAVE</button>
      </div>
      <div className="tool-grid">
        <button onClick={() => run("BRIDGE", getDeviceBridgeHealth)}>BRIDGE</button>
        <button onClick={() => run("ANDROID", async () => {
          const data = await getAndroidDevices();
          const first = data.devices?.[0]?.serial;
          if (first) setSelected(first);
          return data;
        })}>ADB DEVICES</button>
        <button onClick={() => run("FASTBOOT", getFastbootDevices)}>FASTBOOT</button>
        <button onClick={() => run("WI-FI", scanWifi)}>WI-FI SCAN</button>
        <button onClick={() => run("BLUETOOTH", scanBluetooth)}>BLE SCAN</button>
        <button onClick={() => run("RADIO / RF", getRadioStatus)}>RADIO / RF</button>
        <button onClick={() => run("RADAR", scanRadar)}>RADAR SCAN</button>
      </div>
      {selected && (
        <div className="tool-grid">
          <button onClick={() => run("INFO", () => getAndroidDeviceInfo(selected))}>DEVICE INFO</button>
          <button onClick={() => run("DIAGNOSTICS", () => getAndroidDiagnostics(selected))}>DIAGNOSTICS</button>
          <button onClick={() => run("BOOT STATE", () => getBootState(selected))}>BOOT STATE</button>
          <button onClick={() => run("REBOOT", () => rebootAndroid(selected, "system"))}>REBOOT SYSTEM</button>
        </div>
      )}
      {result && (
        <div className="device-result">
          <strong>{result.label}: {result.status}</strong>
          {result.data?.findings ? (
            <div className="tracked-device-list">
              {result.data.findings.length === 0 ? (
                <span className="notice">No local devices detected by the available sensors.</span>
              ) : (
                result.data.findings.slice(0, 20).map((device, index) => (
                  <article className="tracked-device" key={(device.label || device.type || "device") + index}>
                    <div>
                      <strong>{device.label || "Unknown device"}</strong>
                      <span>{String(device.type || "device").toUpperCase()} · {device.source || "LOCAL"}</span>
                    </div>
                    <div>
                      <span>SIGNAL {device.signal ?? "N/A"}</span>
                      <span>
                        DIST {Number.isFinite(device.distance_estimate_m) ? device.distance_estimate_m + "m" : "N/A"}
                      </span>
                      <span>DIR {device.direction || "UNKNOWN"}</span>
                      <span>CONF {Number.isFinite(device.distance_confidence) ? device.distance_confidence + "%" : "N/A"}</span>
                    </div>
                  </article>
                ))
              )}
            </div>
          ) : (
            <pre>{result.error || JSON.stringify(result.data, null, 2)}</pre>
          )}
        </div>
      )}
      <p className="notice">
        Tracking reports only locally discoverable devices. BLE distance is an approximate RSSI estimate; direction stays UNKNOWN until hardware can provide bearing.
      </p>
    </section>
  );
}
