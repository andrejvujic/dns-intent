import { useCallback, useEffect, useState } from 'react';

import { attachPanicSignature, getPanicChanges, votePanicChange } from '../api/domains.js';

function downloadJson(change) {
  const blob = new Blob([`${JSON.stringify(change, null, 2)}\n`], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${change.domain}-${change.operation.toLowerCase()}-panic.json`;
  link.click();
  URL.revokeObjectURL(url);
}

function changeSummary(change) {
  if (change.operation === 'CANCEL_COMMIT') return `Cancel scheduled commit #${change.commit_id}`;
  if (change.operation === 'ADD_RECORD') return `Add ${change.record_type} record`;
  return `${change.operation === 'UPDATE_RECORD' ? 'Update' : 'Delete'} DNS record #${change.record_id}`;
}

export default function PendingPanicChanges({ userId, domainId, onNotify, onApplied }) {
  const [items, setItems] = useState([]);
  const [signatures, setSignatures] = useState({});
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { setItems(await getPanicChanges(userId, domainId)); }
    catch (error) { onNotify('error', error.message); }
    finally { setLoading(false); }
  }, [domainId, onNotify, userId]);

  useEffect(() => { load(); }, [load]);

  async function loadSignatureFile(itemId, event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      const value = parsed.signature || parsed.panic_signature || parsed.panic_request?.signature;
      if (typeof value !== 'string') throw new Error('missing signature');
      setSignatures((current) => ({ ...current, [itemId]: value }));
    } catch {
      onNotify('error', 'Signature file must contain a signature field.');
      event.target.value = '';
    }
  }

  async function attach(item) {
    const signature = (signatures[item.id] || '').trim();
    if (!signature) return onNotify('error', 'Paste or upload your panic signature first.');
    setBusyId(item.id);
    try {
      await attachPanicSignature(userId, domainId, item.id, signature);
      onNotify('success', 'Your panic signature is valid. You can now vote.');
      await load();
    } catch (error) { onNotify('error', error.message); }
    finally { setBusyId(null); }
  }

  async function vote(item, decision) {
    const signature = (signatures[item.id] || '').trim();
    setBusyId(item.id);
    try {
      const updated = await votePanicChange(userId, domainId, item.id, decision, signature);
      onNotify('success', `Vote recorded: ${decision}. ${updated.status === 'APPLIED' ? 'Quorum was reached and the change was applied.' : ''}`);
      await load();
      if (updated.status === 'APPLIED') await onApplied();
    } catch (error) { onNotify('error', error.message); }
    finally { setBusyId(null); }
  }

  if (loading) return <div className="loading-state">Loading panic changes…</div>;
  return (
    <section className="scheduled-commits panic-board">
      <div className="commit-list-heading">
        <div><p className="policy-kicker">Emergency quorum</p><h2>Pending Panic Changes</h2></div>
        <button type="button" onClick={load}>Refresh</button>
      </div>
      <p className="commit-help">Review the requested operation, sign the exact JSON with your panic key, then cast one final vote.</p>
      {items.length === 0 ? <p className="commit-empty">No panic changes have been submitted.</p> : (
        <div className="commit-list">
          {items.map((item) => <article className="commit-item" key={item.id}>
            <div className="commit-item-top">
              <span className={`commit-status panic-status status-${item.status.toLowerCase()}`}>PANIC · {item.status}</span>
              <span>Requested by {item.created_by_username}</span>
            </div>
            <h3>{changeSummary(item.change)}</h3>
            <code>{item.hash}</code>
            <dl className="panic-quorum-grid">
              <div><dt>Accepted</dt><dd>{item.for_count} / {item.required_quorum}</dd></div>
              <div><dt>Rejected</dt><dd>{item.against_count} / {item.required_quorum}</dd></div>
            </dl>
            <details className="panic-json-review"><summary>Review requested JSON</summary><pre>{JSON.stringify(item.change, null, 2)}</pre></details>
            <button className="commit-reveal-button panic-download-button" type="button" onClick={() => downloadJson(item.change)}>Download JSON to sign</button>
            {item.status === 'PENDING' && !item.user_vote && <div className="reveal-form panic-vote-form">
              <p className="reveal-step-label">Signature and vote</p>
              <label htmlFor={`panic-signature-${item.id}`}>Panic signature</label>
              <textarea id={`panic-signature-${item.id}`} rows={3} value={signatures[item.id] || ''} onChange={(event) => setSignatures((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="88-character Base64 Ed25519 signature" />
              <label htmlFor={`panic-signature-file-${item.id}`}>Or upload signature bundle</label>
              <input id={`panic-signature-file-${item.id}`} type="file" accept="application/json,.json" onChange={(event) => loadSignatureFile(item.id, event)} />
              {!item.user_has_signed ? (
                <div className="reveal-actions"><button type="button" disabled={busyId === item.id} onClick={() => attach(item)}>Validate signature</button></div>
              ) : (
                <>
                  <p className="field-note">Signature verified. Your vote is final and can be submitted only once.</p>
                  <div className="reveal-actions panic-vote-actions">
                    <button type="button" disabled={busyId === item.id} onClick={() => vote(item, 'REJECT')}>ODBIJ</button>
                    <button type="submit" disabled={busyId === item.id} onClick={() => vote(item, 'ACCEPT')}>PRIHVATI</button>
                  </div>
                </>
              )}
            </div>}
            {item.user_vote && <div className="panic-user-vote"><span>✓</span><p>Your vote: <strong>{item.user_vote}</strong>{item.created_by_user_id === userId ? ' · recorded automatically as the request author' : ''}</p></div>}
          </article>)}
        </div>
      )}
    </section>
  );
}
