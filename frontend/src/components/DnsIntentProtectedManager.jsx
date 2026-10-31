import DnsRecordTable from './DnsRecordTable.jsx';

function policyValue(value, fallback = 'Not configured') {
  return value === undefined || value === null || value === '' ? fallback : value;
}

export default function DnsIntentProtectedManager({ ieRecord, records, query, onQueryChange }) {
  const policy = ieRecord.value || {};
  const operations = Array.isArray(policy.protected_operations)
    ? policy.protected_operations.join(', ')
    : policyValue(policy.protected_operations);

  return (
    <>
      <section className="intent-notice" role="status">
        <span className="intent-notice-icon" aria-hidden="true">✓</span>
        <div>
          <strong>DNS Intent is enabled for this domain.</strong>
          <p>DNS record changes must use the commit/reveal or panic flow.</p>
        </div>
      </section>

      <section className="intent-policy-card">
        <div>
          <p className="policy-kicker">DNS Intent policy</p>
          <h2>Protected change policy</h2>
        </div>
        <dl className="policy-grid">
          <div><dt>Delay</dt><dd>{policyValue(policy.delay_seconds, 0)} seconds</dd></div>
          <div><dt>Panic quorum</dt><dd>{policyValue(policy.panic_quorum)}</dd></div>
          <div><dt>Protected operations</dt><dd>{operations}</dd></div>
        </dl>
        <div className="protected-flow-placeholder">
          Commit/reveal and panic controls will appear here when backend endpoints become available.
        </div>
      </section>

      <section className="records-panel">
        <div className="records-toolbar">
          <h2>DNS records</h2>
          <label className="record-search">
            <span aria-hidden="true">⌕</span>
            <input
              type="search"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="Search records"
              aria-label="Search DNS records"
            />
          </label>
        </div>
        <DnsRecordTable records={records} dnsIntentEnabled />
      </section>
    </>
  );
}
