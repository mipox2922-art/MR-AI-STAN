const LINKS = [
  {
    title: "Google Security Checkup",
    description: "Kagua devices, sign-ins na security settings za Google Account yako.",
    url: "https://myaccount.google.com/security-checkup",
  },
  {
    title: "Google Recent Security Events",
    description: "Angalia matukio ya usalama ya hivi karibuni kwenye Google Account.",
    url: "https://myaccount.google.com/notifications",
  },
  {
    title: "Gmail Activity",
    description: "Gmail yenyewe inaonyesha last account activity pamoja na recent IP addresses.",
    url: "https://mail.google.com/",
  },
];

export default function SecurityHub() {
  return (
    <section className="panel large-panel security-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">GOOGLE PROTECTION</span>
          <h2>Account Security Console</h2>
        </div>
        <span className="badge">OFFICIAL GOOGLE LINKS</span>
      </div>

      <div className="security-grid">
        {LINKS.map(link => (
          <article className="security-card" key={link.title}>
            <div className="security-icon">🛡</div>
            <div>
              <strong>{link.title}</strong>
              <span>{link.description}</span>
            </div>
            <button
              className="mini-button"
              onClick={() => window.open(link.url, "_blank", "noopener,noreferrer")}
            >
              OPEN
            </button>
          </article>
        ))}
      </div>

      <div className="security-note">
        <strong>REALITY CHECK</strong>
        <span>
          Google can show recent Gmail access IPs and approximate locations in
          its own account-activity view. Exact GPS tracking requires a real
          location source and user/device authorization.
        </span>
      </div>
    </section>
  );
}
