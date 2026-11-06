import { useCallback, useEffect, useState } from "react";
import {
  getShopStatus,
  getShopOverview,
  getShopProducts,
  getShopOrders,
} from "../api";

function money(cents) {
  if (!Number.isFinite(Number(cents))) return "Unknown";
  return "USD " + (Number(cents) / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function date(value) {
  if (!value) return "Not recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "Not recorded"
    : parsed.toLocaleString("en-GB", { timeZone: "Africa/Dar_es_Salaam" });
}

export default function ShopManager() {
  const [status, setStatus] = useState(null);
  const [overview, setOverview] = useState(null);
  const [products, setProducts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const connection = await getShopStatus();
      setStatus(connection);
      if (connection.status !== "CONNECTED") {
        setOverview(null);
        setProducts([]);
        setOrders([]);
        return;
      }
      const [summary, catalog, recentOrders] = await Promise.all([
        getShopOverview(),
        getShopProducts(40),
        getShopOrders(20),
      ]);
      setOverview(summary.overview || null);
      setProducts(Array.isArray(catalog.products) ? catalog.products : []);
      setOrders(Array.isArray(recentOrders.orders) ? recentOrders.orders : []);
    } catch (err) {
      setError(err.message || "343Shop could not be reached.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const productSummary = overview?.products || {};
  const orderSummary = overview?.orders || {};

  return (
    <>
      <section className="panel large-panel">
        <div className="panel-head">
          <div>
            <span className="eyebrow">MOG343 · STORE OPERATIONS</span>
            <h2>343Shop Manager</h2>
            <p>MR AI's private store connection for catalog, order and performance audits.</p>
          </div>
          <span className="badge">{status?.status || "CHECKING"}</span>
        </div>
        <div className="settings-actions" style={{ gap: 10, flexWrap: "wrap" }}>
          <a href="https://343shop.chugastan343.workers.dev/#marketplaces" target="_blank" rel="noreferrer">OPEN 343SHOP ↗</a>
          <button type="button" className="mini-button" onClick={refresh} disabled={busy}>
            {busy ? "CHECKING STORE..." : "REFRESH STORE"}
          </button>
        </div>
        {status && <p className="tool-status" role="status">{status.message}</p>}
        {error && <p className="auth-error" role="alert">{error}</p>}
        {status?.status !== "CONNECTED" && (
          <p>
            Store data is not being displayed because the private API health check has not passed.
            Configure the matching MR_AI_SHOP_API_KEY on the shop runtime and SHOP_API_KEY on the MR AI backend.
          </p>
        )}
        {overview && (
          <>
            <div className="service-grid" style={{ marginTop: 14 }}>
              <div className="service-card"><span>PRODUCTS</span><strong>{productSummary.total ?? 0}</strong><small>{productSummary.active ?? 0} active · {productSummary.inactive ?? 0} inactive</small></div>
              <div className="service-card"><span>OWN PRODUCTS</span><strong>{productSummary.own ?? 0}</strong><small>Made / fulfilled by the store</small></div>
              <div className="service-card"><span>PARTNER PRODUCTS</span><strong>{productSummary.partner ?? 0}</strong><small>External partner listings</small></div>
              <div className="service-card"><span>RECORDED ORDERS</span><strong>{orderSummary.total ?? 0}</strong><small>{orderSummary.pendingPayment ?? 0} pending payment</small></div>
            </div>
            <p className="tool-status">Last store snapshot: {date(overview.generated_at)} · Currency: {overview.currency || "USD"}</p>
            <div className="panel-head"><h2>Recent orders</h2><span className="badge">{orders.length} LOADED</span></div>
            <div className="job-results" style={{ display: "grid", gap: 10 }}>
              {orders.map(order => (
                <article className="agent-card" key={order.id}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                    <strong>{order.id}</strong>
                    <span className="badge">{String(order.status || "UNKNOWN").toUpperCase()}</span>
                  </div>
                  <small>{order.customerName || "Customer name not recorded"} · {date(order.createdAt)}</small>
                  <p>{(order.items || []).map(item => item.name + " × " + item.qty).join(", ") || "No line items returned"}</p>
                  <strong>{money(order.totals?.totalCents)}</strong>
                </article>
              ))}
              {!orders.length && <div className="empty">No orders were returned by the private store API.</div>}
            </div>
          </>
        )}
      </section>

      {overview && (
        <section className="panel large-panel" style={{ marginTop: 16 }}>
          <div className="panel-head"><div><span className="eyebrow">CATALOG AUDIT</span><h2>Products</h2></div><span className="badge">{products.length} LOADED</span></div>
          <div className="job-results" style={{ display: "grid", gap: 10 }}>
            {products.map(product => (
              <article className="agent-card" key={product.slug}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                  <strong>{product.name}</strong>
                  <span className="badge">{product.active === false ? "INACTIVE" : "ACTIVE"}</span>
                </div>
                <small>{product.slug} · {product.category} · {product.type}</small>
                <p>{product.description || product.descriptionSw || "No description recorded."}</p>
                <strong>{money(product.priceCents)}</strong>
              </article>
            ))}
            {!products.length && <div className="empty">No products returned by the private store API.</div>}
          </div>
          <p style={{ opacity: 0.8, marginTop: 14 }}>
            This view is read-only. Pending-payment amounts are not verified revenue. The current store catalog does not provide stock quantities.
          </p>
        </section>
      )}
    </>
  );
}
