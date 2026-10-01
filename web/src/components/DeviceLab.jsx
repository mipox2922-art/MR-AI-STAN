import { useState } from "react";
import {
  getDeviceBridgeHealth,
  getAndroidDevices,
  getFastbootDevices,
  scanBluetooth,
  getAndroidDeviceInfo,
  getAndroidDiagnostics,
  rebootAndroid,
  setBridgeToken
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
        <button onClick={() => run("BLUETOOTH", scanBluetooth)}>BLE SCAN</button>
      </div>
      {selected && (
        <div className="tool-grid">
          <button onClick={() => run("INFO", () => getAndroidDeviceInfo(selected))}>DEVICE INFO</button>
          <button onClick={() => run("DIAGNOSTICS", () => getAndroidDiagnostics(selected))}>DIAGNOSTICS</button>
          <button onClick={() => run("REBOOT", () => rebootAndroid(selected, "system"))}>REBOOT SYSTEM</button>
        </div>
      )}
      {result && (
        <div className="device-result">
          <strong>{result.label}: {result.status}</strong>
          <pre>{result.error || JSON.stringify(result.data, null, 2)}</pre>
        </div>
      )}
      <p className="notice">
        Device actions are intended for devices you own or are explicitly authorized to administer.
      </p>
    </section>
  );
}
