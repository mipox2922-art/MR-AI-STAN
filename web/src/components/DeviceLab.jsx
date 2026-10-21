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
  scanRadar,
  recordActivityEvent
} from "../api";

export default function DeviceLab() {
  const [token, setToken] = useState(localStorage.getItem("mr_ai_bridge_token") || "");
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState("");
  const [running, setRunning] = useState(false);

  async function run(label, fn) {
    if (running) return;
    const action = String(label || "DEVICE_ACTION").toUpperCase().replace(/[^A-Z0-9_.:-]/g, "_").slice(0, 80);
    const requestId = \`device-\${Date.now()}-\${Math.random().toString(36).slice(2)}\`;

    try {
      await recordActivityEvent({
        component: "device", action, outcome: "REQUESTED", risk: "HIGH", request_id: requestId,
      });
    } catch (error) {
      setResult({ label, status: "ERROR", error: "Audit log haipatikani; kitendo kimezuiwa. " + error.message });
      return;
    }

    const approved = window.confirm(
      \`BOSS FERISI: Idhini inahitajika kwa kila kitendo cha Device Lab.\n\nKitendo: \${label}\nKifaa kilichochaguliwa: \${selected || "hakijachaguliwa"}\n\nKuendelea?\`
    );
    if (!approved) {
      await recordActivityEvent({
        component: "device", action, outcome: "REJECTED", risk: "HIGH", request_id: requestId,
      }).catch(() => {});
      setResult({ label, status: "REJECTED", error: "Boss hakuidhinisha; hakukuwa na kitendo cha kifaa." });
      return;
    }

    try {
      await recordActivityEvent({
        component: "device", action, outcome: "APPROVED", risk: "HIGH", request_id: requestId,
      });
    } catch (error) {
      setResult({ label, status: "ERROR", error: "Idhini haikuweza kuhifadhiwa kwenye audit log; kitendo kimezuiwa. " + error.message });
      return;
    }

    setRunning(true);
    setResult({ label, status: "RUNNING" });
    let data;
    try {
      data = await fn();
    } catch (error) {
      await recordActivityEvent({
        component: "device", action, outcome: "FAILED", risk: "HIGH", request_id: requestId,
      }).catch(() => {});
      setResult({ label, status: "ERROR", error: error.message });
      setRunning(false);
      return;
    }

    const verified = data?.verified === true || data?.status === "COMPLETED" || data?.status === "CONNECTED";
    try {
      await recordActivityEvent({
        component: "device", action, outcome: verified ? "VERIFIED" : "DISPATCHED_UNVERIFIED",
        risk: "HIGH", request_id: requestId,
      });
    } catch (error) {
      // The device call already returned. Do not relabel a real outcome as an execution failure
      // merely because the result audit could not be persisted afterward.
      setResult({ label, status: "UNVERIFIED", data,
        error: "Kitendo kilirudisha matokeo, lakini audit ya matokeo haikuhifadhiwa: " + error.message });
      setRunning(false);
      return;
    }
    setResult({ label, status: verified ? "COMPLETED" : "UNVERIFIED", data });
    setRunning(false);
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
        <button disabled={running} onClick={() => run("BRIDGE", getDeviceBridgeHealth)}>BRIDGE</button>
        <button disabled={running} onClick={() => run("ANDROID", async () => {
          const data = await getAndroidDevices();
          const first = data.devices?.[0]?.serial;
          if (first) setSelected(first);
          return data;
        })}>ADB DEVICES</button>
        <button disabled={running} onClick={() => run("FASTBOOT", getFastbootDevices)}>FASTBOOT</button>
        <button disabled={running} onClick={() => run("WI-FI", scanWifi)}>WI-FI SCAN</button>
        <button disabled={running} onClick={() => run("BLUETOOTH", scanBluetooth)}>BLE SCAN</button>
        <button disabled={running} onClick={() => run("RADIO / RF", getRadioStatus)}>RADIO / RF</button>
        <button disabled={running} onClick={() => run("RADAR", scanRadar)}>RADAR SCAN</button>
      </div>
      {selected && (
        <div className="tool-grid">
          <button disabled={running} onClick={() => run("INFO", () => getAndroidDeviceInfo(selected))}>DEVICE INFO</button>
          <button disabled={running} onClick={() => run("DIAGNOSTICS", () => getAndroidDiagnostics(selected))}>DIAGNOSTICS</button>
          <button disabled={running} onClick={() => run("BOOT STATE", () => getBootState(selected))}>BOOT STATE</button>
          <button disabled={running} onClick={() => {
          if (window.confirm(`Reboot Android device ${selected}? Unsaved work may be lost.`)) {
            run("REBOOT", () => rebootAndroid(selected, "system"));
          }
        }}>REBOOT SYSTEM</button>
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
