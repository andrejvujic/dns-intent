import { useMemo, useState } from 'react';

const HIGH_RISK_TYPES = new Set(['NS', 'DS', 'DNSKEY']);

function recordName(record) {
  return record.value?.name || '@';
}

function recordContent(record) {
  const value = record.value || {};
  return value.address || value.host || value.exchange || value.target || value.content || value.value || '—';
}

export default function DomainConfiguration({ domain, isLoading, onBack }) {
  const [query, setQuery] = useState('');
  const filteredRecords = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery || !domain) return domain?.records || [];

    return domain.records.filter((record) => (
      `${record.type} ${recordName(record)} ${recordContent(record)}`
        .toLowerCase()
        .includes(normalizedQuery)
    ));
  }, [domain, query]);

  if (isLoading || !domain) {
    return <div className="page-container"><div className="loading-state">Loading DNS configuration…</div></div>;
  }

  return (
    <div className="page-container">
      <button className="back-button" type="button" onClick={onBack}>← All domains</button>

      <section className="page-heading domain-heading">
        <h1>{domain.name}</h1>
      </section>

      <section className="records-panel">
        <div className="records-toolbar">
          <h2>DNS records</h2>
          <label className="record-search">
            <span aria-hidden="true">⌕</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search records"
              aria-label="Search DNS records"
            />
          </label>
        </div>

        <div className="table-scroll">
          <table className="records-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Name</th>
                <th>Content</th>
                <th>TTL</th>
                <th>Priority</th>
                <th>Protection</th>
              </tr>
            </thead>
            <tbody>
              {filteredRecords.map((record) => (
                <tr key={record.id}>
                  <td><span className={`record-type type-${record.type.toLowerCase()}`}>{record.type}</span></td>
                  <td className="record-name">{recordName(record)}</td>
                  <td><code>{recordContent(record)}</code></td>
                  <td>{record.value?.ttl ?? 'Auto'}</td>
                  <td>{record.value?.priority ?? '—'}</td>
                  <td>
                    {HIGH_RISK_TYPES.has(record.type) ? (
                      <span className="protected-label">Intent required</span>
                    ) : (
                      <span className="standard-label">Standard</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filteredRecords.length === 0 && (
            <div className="table-empty">No records match your search.</div>
          )}
        </div>
      </section>
    </div>
  );
}
