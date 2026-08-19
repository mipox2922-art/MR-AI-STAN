export default function Status({ status }) {
  if (!status) return null;

  return (
    <div className="status-panel">
      <div className="panel-title">
        SYSTEM STATUS
      </div>

      {Object.entries(status).map(([key, value]) => (
        <div className="status-row" key={key}>
          <span>{key.replaceAll("_", " ")}</span>
          <strong className={`status-${value.toLowerCase()}`}>
            {value}
          </strong>
        </div>
      ))}
    </div>
  );
}
