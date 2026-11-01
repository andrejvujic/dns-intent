import { useCallback, useEffect, useState } from 'react';

import { attachPanicSignature, finalizeKeyRotation, finalizeMemberAddition, getDomainMembers, getPanicChanges, votePanicChange } from '../api/domains.js';
import { downloadPrivateKeys, generateDomainKeys, generateMemberKeys, publicKeysPayload } from '../crypto/keys.js';

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
  if (change.operation === 'DISABLE_DNS_INTENT') return 'Disable DNS Intent and clear scheduled changes';
  if (change.operation === 'ROTATE_KEYS') return 'Rotate Intent and panic keys and clear scheduled changes';
  if (change.operation === 'ADD_MEMBER') return `Add ${change.member_email} to the domain`;
  if (change.operation === 'CANCEL_COMMIT') return `Cancel scheduled commit #${change.commit_id}`;
  if (change.operation === 'ADD_RECORD') return `Add ${change.record_type} record`;
  return `${change.operation === 'UPDATE_RECORD' ? 'Update' : 'Delete'} DNS record #${change.record_id}`;
}

export default function PendingPanicChanges({ userId, domainId, domainName, onNotify, onApplied, onChanged }) {
  const [items, setItems] = useState([]);
  const [signatures, setSignatures] = useState({});
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [memberKeyFiles, setMemberKeyFiles] = useState({});

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
      await onChanged?.();
      if (updated.status === 'APPLIED') await onApplied();
    } catch (error) { onNotify('error', error.message); }
    finally { setBusyId(null); }
  }

  async function applyMemberAddition(item) {
    setBusyId(item.id);
    try {
      if (!item.member || item.member.id !== item.change.member_user_id) {
        throw new Error('The invited member details are unavailable. Refresh the request and try again.');
      }
      const keyFile = memberKeyFiles[item.id] || await generateMemberKeys({ name: domainName }, item.member);
      setMemberKeyFiles((current) => ({ ...current, [item.id]: keyFile }));
      const [publicKeys] = publicKeysPayload(keyFile);
      await finalizeMemberAddition(userId, domainId, item.id, publicKeys);
      downloadPrivateKeys(keyFile, `member-${item.member.id}-private-keys`);
      onNotify('success', `${item.change.member_email} was added, their public keys were saved, and their private-key JSON was downloaded.`);
      await load();
      await onApplied();
    } catch (error) { onNotify('error', error.message); }
    finally { setBusyId(null); }
  }

  async function generateRotationKeys(item) {
    setBusyId(item.id);
    try {
      const members = await getDomainMembers(userId, domainId);
      const keyFile = await generateDomainKeys({ name: domainName }, members);
      downloadPrivateKeys(keyFile, 'rotated-private-keys');
      await finalizeKeyRotation(userId, domainId, item.id, publicKeysPayload(keyFile));
      onNotify('success', 'New private keys were downloaded and the public keys were rotated. Store the JSON securely.');
      await load();
      await onApplied();
    } catch (error) {
      onNotify('error', error.message);
    } finally {
      setBusyId(null);
    }
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
          {items.map((item) => {
            const isTied = item.status === 'PENDING' && item.for_count > 0 && item.for_count === item.against_count;
            return <article className="commit-item" key={item.id}>
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
            {isTied && <div className="panic-tie-notice"><strong>Voting is tied.</strong><span>The next vote is the tie-breaker.</span></div>}
            {item.status === 'APPLIED' && <div className="panic-decision-notice decision-accepted"><strong>Decision reached: ACCEPT</strong><span>The acceptance quorum was met and the change was applied.</span></div>}
            {item.status === 'QUORUM_REACHED' && item.change.operation === 'ROTATE_KEYS' && (
              <div className="panic-decision-notice decision-accepted">
                <strong>Rotation approved</strong>
                <span>
                  {item.created_by_user_id === userId
                    ? 'The quorum was met. You initiated this action; generate and apply the new keys.'
                    : `Waiting for ${item.created_by_username}, who initiated this action, to generate and apply the new keys.`}
                </span>
              </div>
            )}
            {item.status === 'QUORUM_REACHED' && item.change.operation === 'ADD_MEMBER' && (
              <div className="panic-decision-notice decision-accepted">
                <strong>Member addition approved</strong>
                <span>{item.created_by_user_id === userId
                  ? 'The signed quorum was met. Apply the addition to generate this member’s keys and download their private-key JSON.'
                  : `Waiting for ${item.created_by_username}, who initiated this invitation, to apply the addition.`}</span>
              </div>
            )}
            {item.status === 'REJECTED' && <div className="panic-decision-notice decision-rejected"><strong>Decision reached: REJECT</strong><span>The rejection quorum was met. No change was applied.</span></div>}
            <details className="panic-json-review"><summary>Review requested JSON</summary><pre>{JSON.stringify(item.change, null, 2)}</pre></details>
            {item.status === 'PENDING' && (
              <button className="commit-reveal-button panic-download-button" type="button" onClick={() => downloadJson(item.change)}>Download JSON to sign</button>
            )}
            {item.status === 'QUORUM_REACHED' && item.change.operation === 'ROTATE_KEYS' && item.created_by_user_id === userId && (
              <button className="primary-button" type="button" disabled={busyId === item.id} onClick={() => generateRotationKeys(item)}>
                {busyId === item.id ? 'Generating keys…' : 'Generate file and rotate keys'}
              </button>
            )}
            {item.status === 'QUORUM_REACHED' && item.change.operation === 'ADD_MEMBER' && item.created_by_user_id === userId && (
              <button className="primary-button" type="button" disabled={busyId === item.id} onClick={() => applyMemberAddition(item)}>
                {busyId === item.id ? 'Generating keys and applying…' : 'Generate keys and apply addition'}
              </button>
            )}
            {item.status === 'APPLIED' && memberKeyFiles[item.id] && (
              <button className="commit-reveal-button panic-download-button" type="button"
                onClick={() => downloadPrivateKeys(memberKeyFiles[item.id], `member-${item.change.member_user_id}-private-keys`)}>
                Download member keys again
              </button>
            )}
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
                    <button className="panic-reject-button" type="button" disabled={busyId === item.id} onClick={() => vote(item, 'REJECT')}><span>✕</span> REJECT</button>
                    <button className="panic-accept-button" type="button" disabled={busyId === item.id} onClick={() => vote(item, 'ACCEPT')}><span>✓</span> ACCEPT</button>
                  </div>
                </>
              )}
            </div>}
            {item.user_vote && <div className="panic-user-vote"><span>✓</span><p>Your vote: <strong>{item.user_vote}</strong>{item.created_by_user_id === userId ? ' · recorded automatically as the request author' : ''}</p></div>}
          </article>;})}
        </div>
      )}
    </section>
  );
}
