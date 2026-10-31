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

export default function IntentGenerator({ domainName, records, protectedTypes, onNotify }) {
  const now = new Date();
  const [operation, setOperation] = useState('ADD_RECORD');
  const [recordId, setRecordId] = useState('');
  const [notBefore, setNotBefore] = useState(() => localDateTime(new Date(now.getTime() - 60_000)));
  const [validUntil, setValidUntil] = useState(() => localDateTime(new Date(now.getTime() + 86_400_000)));
  const [showRecordForm, setShowRecordForm] = useState(false);

  const protectedRecords = useMemo(
    () => records.filter((record) => protectedTypes.includes(record.type)),
    [protectedTypes, records],
  );
  const selectedRecord = protectedRecords.find((record) => record.id === Number(recordId));

  function timeFields() {
    const start = new Date(notBefore);
    const end = new Date(validUntil);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      onNotify('error', 'Unesite ispravan vremenski period intenta.');
      return null;
    }
    if (end <= start) {
      onNotify('error', 'Valid until mora biti poslije Not before vremena.');
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
    if (operation === 'ADD_RECORD') {
      intent = {
        domain: domainName,
        operation,
        record_type: recordPayload.type,
        value: recordPayload.value,
        ...times,
      };
    } else {
      if (!selectedRecord) {
        onNotify('error', 'Izaberite DNS zapis.');
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
    downloadJson(`${safeDomain}-${operation.toLowerCase()}-intent.json`, intent);
    onNotify('success', 'Intent JSON je generisan i preuzet. Potpišite ga lokalno.');
    return true;
  }

  function handleGenerate(event) {
    event.preventDefault();
    if (!timeFields()) return;
    if (operation !== 'ADD_RECORD' && !selectedRecord) {
      onNotify('error', 'Izaberite DNS zapis.');
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
        <h2>Generiši Intent JSON</h2>
        <p className="commit-help">Izaberite operaciju i period važenja. Vrijeme se pri preuzimanju pretvara u UTC ISO format.</p>
      </div>
      <form onSubmit={handleGenerate}>
        <label>
          <span>Operacija</span>
          <select value={operation} onChange={(event) => {
            setOperation(event.target.value);
            setRecordId('');
          }}>
            <option value="ADD_RECORD">Dodaj zapis</option>
            <option value="UPDATE_RECORD">Izmijeni zapis</option>
            <option value="DELETE_RECORD">Obriši zapis</option>
          </select>
        </label>
        {operation !== 'ADD_RECORD' && (
          <label>
            <span>Zaštićeni DNS zapis</span>
            <select value={recordId} onChange={(event) => setRecordId(event.target.value)} required>
              <option value="">Izaberite zapis</option>
              {protectedRecords.map((record) => (
                <option value={record.id} key={record.id}>
                  #{record.id} · {record.type} · {record.value.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="intent-time-grid">
          <label>
            <span>Not before</span>
            <input type="datetime-local" value={notBefore} onChange={(event) => setNotBefore(event.target.value)} required />
          </label>
          <label>
            <span>Valid until</span>
            <input type="datetime-local" value={validUntil} onChange={(event) => setValidUntil(event.target.value)} required />
          </label>
        </div>
        <button className="primary-button" type="submit">Unesi DNS podatke i preuzmi JSON</button>
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
        />
      )}
    </section>
  );
}
