import { useCallback, useEffect, useState } from 'react';

import { createPanicChange, getScheduledCommits, revealCommit, scheduleCommit } from '../api/domains.js';
import IntentGenerator from './IntentGenerator.jsx';

function policyValue(value, fallback = 'Not configured') {
  return value === undefined || value === null || value === '' ? fallback : value;
}

function formatDate(value) {
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(value));
}

export default function DnsIntentProtectedManager({ ieRecord, userId, domainId, domainName, records, onNotify, onApplied }) {
  const policy = ieRecord.value || {};
  const [hash, setHash] = useState('');
  const [signature, setSignature] = useState('');
  const [commits, setCommits] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [revealingId, setRevealingId] = useState(null);
  const [intent, setIntent] = useState(null);
  const [intentFilename, setIntentFilename] = useState('');
  const [nonce, setNonce] = useState('');
  const [isApplying, setIsApplying] = useState(false);
  const [panicMode, setPanicMode] = useState(false);
  const [panicChange, setPanicChange] = useState(null);
  const operations = Array.isArray(policy.protected_operations)
    ? policy.protected_operations.join(', ')
    : policyValue(policy.protected_operations);

  const loadCommits = useCallback(async () => {
    setIsLoading(true);
    try {
      setCommits(await getScheduledCommits(userId, domainId));
    } catch (error) {
      onNotify('error', error.message);
    } finally {
      setIsLoading(false);
    }
  }, [domainId, onNotify, userId]);

  useEffect(() => {
    loadCommits();
  }, [loadCommits]);

  async function handleSubmit(event) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      if (panicMode) {
        if (!panicChange) throw new Error('Select the Panic Change JSON file.');
        await createPanicChange(userId, domainId, { change: panicChange, ...(hash.trim() ? { hash: hash.trim() } : {}), signature: signature.trim() });
      } else {
        await scheduleCommit(userId, domainId, { hash: hash.trim(), signature: signature.trim() });
      }
      setHash('');
      setSignature('');
      setPanicChange(null);
      onNotify('success', panicMode ? 'The panic change was submitted for quorum voting.' : 'The commit was scheduled and its hold period has started.');
      await loadCommits();
    } catch (error) {
      onNotify('error', error.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function loadSigningBundle(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const bundle = JSON.parse(await file.text());
      const commit = bundle.panic_request || bundle.commit_request || bundle;
      if (typeof commit.hash !== 'string' || typeof commit.signature !== 'string') {
        throw new Error('missing fields');
      }
      setHash(commit.hash);
      setSignature(commit.signature);
      onNotify('success', 'The hash and signature were loaded from the signing bundle.');
    } catch {
      event.target.value = '';
      onNotify('error', 'The signing bundle must contain commit_request.hash and commit_request.signature.');
    }
  }

  async function loadPanicChange(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      if (parsed.type !== 'PANIC_CHANGE') throw new Error('wrong type');
      setPanicChange(parsed);
    } catch {
      event.target.value = '';
      setPanicChange(null);
      onNotify('error', 'Select a valid PANIC_CHANGE JSON file.');
    }
  }

  function openReveal(commitId) {
    setRevealingId(commitId);
    setIntent(null);
    setIntentFilename('');
    setNonce('');
  }

  async function loadIntentFile(event) {
    const file = event.target.files?.[0];
    if (!file) {
      setIntent(null);
      setIntentFilename('');
      return;
    }
    try {
      const parsed = JSON.parse(await file.text());
      setIntent(parsed);
      setIntentFilename(file.name);
    } catch {
      event.target.value = '';
      setIntent(null);
      setIntentFilename('');
      onNotify('error', 'The selected Intent file is not valid JSON.');
    }
  }

  async function handleReveal(event) {
    event.preventDefault();
    if (!intent) {
      onNotify('error', 'Select the original Intent JSON file.');
      return;
    }

    setIsApplying(true);
    try {
      await revealCommit(userId, domainId, revealingId, {
        intent,
        nonce: nonce.trim(),
      });
      onNotify('success', 'The commit was revealed and the DNS change was applied.');
      setRevealingId(null);
      setIntent(null);
      setIntentFilename('');
      setNonce('');
      await loadCommits();
      onApplied().catch((error) => {
        onNotify('error', `The change was applied, but refreshing the domain failed: ${error.message}`);
      });
    } catch (error) {
      onNotify('error', error.message);
    } finally {
      setIsApplying(false);
    }
  }

  return (
    <>
      <section className="intent-notice" role="status">
        <span className="intent-notice-icon" aria-hidden="true">✓</span>
        <div>
          <strong>DNS Intent is enabled for this domain.</strong>
          <p>Protected record types require the commit/reveal or panic flow; others can still change directly.</p>
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
      </section>

      <IntentGenerator
        domainName={domainName}
        records={records}
        protectedTypes={Array.isArray(policy.protected_operations) ? policy.protected_operations : []}
        commits={commits}
        panicMode={panicMode}
        onPanicModeChange={(enabled) => { setPanicMode(enabled); setHash(''); setSignature(''); setPanicChange(null); }}
        onNotify={onNotify}
      />

      <section className="commit-workspace">
        <form className="commit-form" onSubmit={handleSubmit}>
          <div>
            <p className="policy-kicker">2. {panicMode ? 'Panic request' : 'Commit'}</p>
            <h2>{panicMode ? 'Submit a signed panic change' : 'Schedule a signed change'}</h2>
            <p className="commit-help">
              Upload the signing bundle or enter its Base64 SHA-256 hash and Ed25519 signature.
              {panicMode ? ' The signature must use your panic key.' : ' The nonce stays local until the reveal phase.'}
            </p>
          </div>
          {panicMode && <><label htmlFor="panic-json">Panic Change JSON</label><input id="panic-json" type="file" accept="application/json,.json" onChange={loadPanicChange} required /></>}
          <label htmlFor="signing-bundle">Signing bundle JSON</label>
          <input
            id="signing-bundle"
            type="file"
            accept="application/json,.json"
            onChange={loadSigningBundle}
          />
          <p className="field-note">Upload the script output, or enter the two values manually below.</p>
          <label htmlFor="commit-hash">{panicMode ? 'Panic hash (optional)' : 'Commit hash'}</label>
          <input
            id="commit-hash"
            value={hash}
            onChange={(event) => setHash(event.target.value)}
            placeholder="44-character Base64 value"
            minLength={44}
            maxLength={44}
            required={!panicMode}
          />
          {panicMode && <p className="field-note">The backend calculates this hash from the uploaded canonical JSON; include it only for an extra consistency check.</p>}
          <label htmlFor="commit-signature">Signature</label>
          <textarea
            id="commit-signature"
            value={signature}
            onChange={(event) => setSignature(event.target.value)}
            placeholder="88-character Base64 Ed25519 signature"
            minLength={88}
            maxLength={88}
            rows={3}
            required
          />
          <button className="primary-button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Submitting…' : panicMode ? 'Submit panic change' : 'Schedule commit'}
          </button>
        </form>

        <div className="scheduled-commits">
          <div className="commit-list-heading">
            <div>
              <p className="policy-kicker">Timeline</p>
              <h2>Scheduled commits</h2>
            </div>
            <button type="button" onClick={loadCommits} disabled={isLoading}>Refresh</button>
          </div>
          {isLoading ? (
            <p className="commit-empty">Loading…</p>
          ) : commits.length === 0 ? (
            <p className="commit-empty">No commits have been scheduled yet.</p>
          ) : (
            <div className="commit-list">
              {commits.map((commit) => (
                <article className="commit-item" key={commit.id}>
                  <div className="commit-item-top">
                    <span className={`commit-status status-${commit.cancellation_pending ? 'blocked' : commit.status.toLowerCase()}`}>
                      {commit.cancellation_pending ? 'CANCELLATION PENDING' : commit.status}
                    </span>
                    <span>{commit.username}</span>
                  </div>
                  <code title={commit.hash}>{commit.hash}</code>
                  <dl>
                    <div><dt>Created</dt><dd>{formatDate(commit.received_at)}</dd></div>
                    <div><dt>Ready at</dt><dd>{formatDate(commit.matures_at)}</dd></div>
                  </dl>
                  {commit.cancellation_pending && (
                    <div className="commit-blocked-notice">
                      <strong>Temporarily blocked</strong>
                      <span>Panic cancellation #{commit.cancellation_panic_id} is being voted on. This commit cannot be applied unless that cancellation is rejected or expires.</span>
                    </div>
                  )}
                  {commit.status === 'READY' && !commit.cancellation_pending && revealingId !== commit.id && (
                    <button
                      className="commit-reveal-button"
                      type="button"
                      onClick={() => openReveal(commit.id)}
                    >
                      Reveal and apply
                    </button>
                  )}
                  {revealingId === commit.id && (
                    <form className="reveal-form" onSubmit={handleReveal}>
                      <p className="reveal-step-label">3. Reveal</p>
                      <label htmlFor={`intent-${commit.id}`}>Original Intent JSON file</label>
                      <input
                        id={`intent-${commit.id}`}
                        type="file"
                        accept="application/json,.json"
                        onChange={loadIntentFile}
                        required
                      />
                      {intentFilename && <small className="intent-file-name">Loaded: {intentFilename}</small>}
                      <label htmlFor={`nonce-${commit.id}`}>Nonce</label>
                      <input
                        id={`nonce-${commit.id}`}
                        value={nonce}
                        onChange={(event) => setNonce(event.target.value)}
                        placeholder="Original Base64 nonce"
                        required
                      />
                      <div className="reveal-actions">
                        <button type="button" onClick={() => setRevealingId(null)}>Cancel</button>
                        <button type="submit" disabled={isApplying}>
                          {isApplying ? 'Applying…' : 'Apply change'}
                        </button>
                      </div>
                    </form>
                  )}
                </article>
              ))}
            </div>
          )}
        </div>
      </section>
    </>
  );
}
