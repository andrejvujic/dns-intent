function joinParts(parts) {
  return parts.filter((part) => part !== undefined && part !== null && part !== '').join(' ');
}

function EditIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m14.7 5.3 4 4M4 20l3.6-.7L19 7.9a1.4 1.4 0 0 0 0-2l-.9-.9a1.4 1.4 0 0 0-2 0L4.7 16.4 4 20Z" />
    </svg>
  );
}

function DeleteIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" />
    </svg>
  );
}

export function recordName(record) {
  return record.value?.name || '@';
}

export function recordContent(record) {
  const value = record.value || {};

  switch (record.type) {
    case 'A':
    case 'AAAA':
      return value.address || '—';
    case 'CNAME':
      return value.target || '—';
    case 'MX':
      return value.exchange || '—';
    case 'TXT':
      return value.text || '—';
    case 'NS':
      return value.host || '—';
    case 'DS':
      return joinParts([value.key_tag, value.algorithm, value.digest_type, value.digest]) || '—';
    case 'DNSKEY':
      return joinParts([value.flags, value.protocol, value.algorithm, value.public_key]) || '—';
    case 'RRSIG':
      return joinParts([
        value.type_covered,
        value.algorithm,
        value.labels,
        value.original_ttl,
        value.signature_expiration,
        value.signature_inception,
        value.key_tag,
        value.signer_name,
        value.signature,
      ]) || '—';
    case 'NSEC':
      return joinParts([value.next_domain_name, ...(value.types || [])]) || '—';
    case 'NSEC3':
      return joinParts([
        value.hash_algorithm,
        value.flags,
        value.iterations,
        value.salt,
        value.next_hashed_owner_name,
        ...(value.types || []),
      ]) || '—';
    case 'CAA':
      return joinParts([value.flags, value.tag, value.value]) || '—';
    default:
      return value.content || value.value || '—';
  }
}

export default function DnsRecordTable({ records, dnsIntentEnabled, isBusy, onEdit, onDelete }) {
  const showActions = !dnsIntentEnabled;

  return (
    <div className="table-scroll">
      <table className="records-table">
        <colgroup>
          <col className="col-type" />
          <col className="col-name" />
          <col className="col-content" />
          <col className="col-ttl" />
          <col className="col-priority" />
          <col className="col-protection" />
          {showActions && <col className="col-actions" />}
        </colgroup>
        <thead>
          <tr>
            <th>Type</th>
            <th>Name</th>
            <th>Content</th>
            <th>TTL</th>
            <th>Priority</th>
            <th>Status / Protection</th>
            {showActions && <th className="actions-heading">Actions</th>}
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr key={record.id}>
              <td><span className={`record-type type-${record.type.toLowerCase()}`}>{record.type}</span></td>
              <td className="record-name">{recordName(record)}</td>
              <td className="record-content"><code title={recordContent(record)}>{recordContent(record)}</code></td>
              <td>{record.value?.ttl ?? 'Auto'}</td>
              <td>{record.value?.priority ?? '—'}</td>
              <td>
                <span className={dnsIntentEnabled ? 'protected-label' : 'direct-label'}>
                  {dnsIntentEnabled ? 'DNS Intent' : 'Direct'}
                </span>
              </td>
              {showActions && (
                <td className="record-actions">
                  <button type="button" onClick={() => onEdit(record)} disabled={isBusy}>
                    <EditIcon />
                    <span>Edit</span>
                  </button>
                  <button className="delete-action" type="button" onClick={() => onDelete(record)} disabled={isBusy}>
                    <DeleteIcon />
                    <span>Delete</span>
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {records.length === 0 && <div className="table-empty">No records match your search.</div>}
    </div>
  );
}
