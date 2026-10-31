import { useMemo, useState } from 'react';

import DnsRecordForm from './DnsRecordForm.jsx';

function localDateTime(date) {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function downloadJson(filename, value) {
  const blob = new Blob([`${JSON.stringify(value, null, 2)}\n`], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function IntentGenerator({ domainName, records, protectedTypes, commits = [], panicMode = false, onPanicModeChange, onNotify }) {
  const now = new Date();
  const [operation, setOperation] = useState('ADD_RECORD');
  const [recordId, setRecordId] = useState('');
  const [notBefore, setNotBefore] = useState(() => localDateTime(new Date(now.getTime() - 60_000)));
  const [validUntil, setValidUntil] = useState(() => localDateTime(new Date(now.getTime() + 86_400_000)));
  const [showRecordForm, setShowRecordForm] = useState(false);
  const [commitId, setCommitId] = useState('');

  const protectedRecords = useMemo(
    () => records.filter((record) => protectedTypes.includes(record.type)),
    [protectedTypes, records],
  );
  const selectedRecord = protectedRecords.find((record) => record.id === Number(recordId));

  function timeFields() {
    const start = new Date(notBefore);
    const end = new Date(validUntil);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      onNotify('error', 'Enter a valid intent time window.');
      return null;
    }
    if (end <= start) {
      onNotify('error', 'Valid until must be later than Not before.');
      return null;
    }
    return {
      not_before: start.toISOString(),
      valid_until: end.toISOString(),
    };
  }

  function saveIntent(recordPayload = null) {
    const times = timeFields();
    if (!times) return false;

    let intent;
    if (panicMode && operation === 'CANCEL_COMMIT') {
      if (!commitId) {
        onNotify('error', 'Select a scheduled commit.');
        return false;
      }
      intent = {
        type: 'PANIC_CHANGE', request_id: crypto.randomUUID(), domain: domainName,
        operation, commit_id: Number(commitId), expires_at: new Date(Date.now() + 86_400_000).toISOString(),
      };
    } else if (panicMode) {
      const base = {
        type: 'PANIC_CHANGE', request_id: crypto.randomUUID(), domain: domainName,
        operation, expires_at: new Date(validUntil).toISOString(),
      };
      if (operation === 'ADD_RECORD') intent = { ...base, record_type: recordPayload.type, value: recordPayload.value };
      else intent = { ...base, record_id: selectedRecord.id, ...(operation === 'UPDATE_RECORD' ? { value: recordPayload.value } : {}) };
    } else if (operation === 'ADD_RECORD') {
      intent = {
        domain: domainName,
        operation,
        record_type: recordPayload.type,
        value: recordPayload.value,
        ...times,
      };
    } else {
      if (!selectedRecord) {
        onNotify('error', 'Select a DNS record.');
        return false;
      }
      intent = {
        domain: domainName,
        operation,
        record_id: selectedRecord.id,
        ...(operation === 'UPDATE_RECORD' ? { value: recordPayload.value } : {}),
        ...times,
      };
    }

    const safeDomain = domainName.replace(/[^a-z0-9.-]/gi, '_');
    downloadJson(`${safeDomain}-${operation.toLowerCase()}-${panicMode ? 'panic' : 'intent'}.json`, intent);
    onNotify('success', `${panicMode ? 'Panic change' : 'Intent'} JSON was generated and downloaded. Sign it locally with your ${panicMode ? 'panic' : 'Intent'} key.`);
    return true;
  }

  function handleGenerate(event) {
    event.preventDefault();
    if (!panicMode && !timeFields()) return;
    if (panicMode && operation !== 'CANCEL_COMMIT' && !timeFields()) return;
    if (panicMode && operation === 'CANCEL_COMMIT') {
      saveIntent();
      return;
    }
    if (operation !== 'ADD_RECORD' && !selectedRecord) {
      onNotify('error', 'Select a DNS record.');
      return;
    }
    if (operation === 'DELETE_RECORD') {
      saveIntent();
      return;
    }
    setShowRecordForm(true);
  }

  async function handleRecordValue(payload) {
    if (saveIntent(payload)) setShowRecordForm(false);
  }

  return (
    <section className="intent-generator">
      <div>
        <p className="policy-kicker">1. Prepare</p>
        <h2>Generate Intent JSON</h2>
        <p className="commit-help">Choose an operation and validity window. Local times are converted to UTC ISO timestamps in the downloaded file.</p>
      </div>
      <form onSubmit={handleGenerate}>
        {onPanicModeChange && (
          <label className="panic-mode-toggle">
            <input type="checkbox" checked={panicMode} onChange={(event) => {
              onPanicModeChange(event.target.checked); setOperation('ADD_RECORD'); setRecordId(''); setCommitId('');
            }} />
            <span><strong>Panic change</strong><small>Uses panic-key voting and executes immediately after quorum.</small></span>
          </label>
        )}
        <label>
          <span>Operation</span>
          <select value={operation} onChange={(event) => {
            setOperation(event.target.value);
            setRecordId('');
          }}>
            <option value="ADD_RECORD">Add record</option>
            <option value="UPDATE_RECORD">Update record</option>
            <option value="DELETE_RECORD">Delete record</option>
            {panicMode && <option value="CANCEL_COMMIT">Cancel scheduled commit</option>}
          </select>
        </label>
        {operation === 'CANCEL_COMMIT' && (
          <label><span>Scheduled commit</span><select value={commitId} onChange={(event) => setCommitId(event.target.value)} required>
            <option value="">Select a commit</option>
            {commits.filter((item) => ['HOLDING', 'READY'].includes(item.status)).map((item) => (
              <option value={item.id} key={item.id}>#{item.id} · {item.username} · {item.status}</option>
            ))}
          </select></label>
        )}
        {operation !== 'ADD_RECORD' && operation !== 'CANCEL_COMMIT' && (
          <label>
            <span>Protected DNS record</span>
            <select value={recordId} onChange={(event) => setRecordId(event.target.value)} required>
              <option value="">Select a record</option>
              {protectedRecords.map((record) => (
                <option value={record.id} key={record.id}>
                  #{record.id} · {record.type} · {record.value.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {operation !== 'CANCEL_COMMIT' && <div className="intent-time-grid">
          <label>
            <span>Not before</span>
            <input type="datetime-local" value={notBefore} onChange={(event) => setNotBefore(event.target.value)} required />
          </label>
          <label>
            <span>Valid until</span>
            <input type="datetime-local" value={validUntil} onChange={(event) => setValidUntil(event.target.value)} required />
          </label>
        </div>}
        <button className="primary-button" type="submit">
          {['DELETE_RECORD', 'CANCEL_COMMIT'].includes(operation) ? `Download ${panicMode ? 'Panic' : 'Intent'} JSON` : 'Continue to record details'}
        </button>
      </form>

      {showRecordForm && (
        <DnsRecordForm
          mode={operation === 'UPDATE_RECORD' ? 'edit' : 'create'}
          record={operation === 'UPDATE_RECORD' ? selectedRecord : null}
          availableTypes={protectedTypes}
          isSubmitting={false}
          onSubmit={handleRecordValue}
          onClose={() => setShowRecordForm(false)}
          onNotify={onNotify}
          kicker="Intent builder"
          title={operation === 'UPDATE_RECORD' ? `Define the new ${selectedRecord?.type || ''} record value` : 'Define the new DNS record'}
          submitLabel="Download Intent JSON"
        />
      )}
    </section>
  );
}
