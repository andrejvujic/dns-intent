import { useCallback, useEffect, useState } from 'react';

import { getScheduledCommits, revealCommit, scheduleCommit } from '../api/domains.js';

function policyValue(value, fallback = 'Not configured') {
  return value === undefined || value === null || value === '' ? fallback : value;
}

function formatDate(value) {
  return new Intl.DateTimeFormat('sr-Latn-RS', {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(value));
}

export default function DnsIntentProtectedManager({ ieRecord, userId, domainId, onNotify, onApplied }) {
  const policy = ieRecord.value || {};
  const [hash, setHash] = useState('');
  const [signature, setSignature] = useState('');
  const [commits, setCommits] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [revealingId, setRevealingId] = useState(null);
  const [intentJson, setIntentJson] = useState('');
  const [nonce, setNonce] = useState('');
  const [isApplying, setIsApplying] = useState(false);
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
      await scheduleCommit(userId, domainId, {
        hash: hash.trim(),
        signature: signature.trim(),
      });
      setHash('');
      setSignature('');
      onNotify('success', 'Commit je zakazan i period čekanja je počeo.');
      await loadCommits();
    } catch (error) {
      onNotify('error', error.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  function openReveal(commitId) {
    setRevealingId(commitId);
    setIntentJson('');
    setNonce('');
  }

  async function handleReveal(event) {
    event.preventDefault();
    let intent;
    try {
      intent = JSON.parse(intentJson);
    } catch {
      onNotify('error', 'Intent mora biti validan JSON.');
      return;
    }

    setIsApplying(true);
    try {
      await revealCommit(userId, domainId, revealingId, {
        intent,
        nonce: nonce.trim(),
      });
      onNotify('success', 'Commit je potvrđen i DNS promjena je primijenjena.');
      setRevealingId(null);
      setIntentJson('');
      setNonce('');
      await loadCommits();
      onApplied().catch((error) => {
        onNotify('error', `Promjena je primijenjena, ali osvježavanje nije uspjelo: ${error.message}`);
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

      <section className="commit-workspace">
        <form className="commit-form" onSubmit={handleSubmit}>
          <div>
            <p className="policy-kicker">Commit phase</p>
            <h2>Zakaži potpisanu promjenu</h2>
            <p className="commit-help">
              Unesite Base64 SHA-256 hash i njegov Ed25519 potpis. Nonce ostaje na
              klijentu i šalje se serveru tek kasnije, zajedno sa intentom, u reveal fazi.
            </p>
          </div>
          <label htmlFor="commit-hash">Commit hash</label>
          <input
            id="commit-hash"
            value={hash}
            onChange={(event) => setHash(event.target.value)}
            placeholder="44 znaka, Base64"
            minLength={44}
            maxLength={44}
            required
          />
          <label htmlFor="commit-signature">Signature</label>
          <textarea
            id="commit-signature"
            value={signature}
            onChange={(event) => setSignature(event.target.value)}
            placeholder="88 znakova, Base64 Ed25519 potpis"
            minLength={88}
            maxLength={88}
            rows={3}
            required
          />
          <button className="primary-button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Zakazivanje…' : 'Zakaži commit'}
          </button>
        </form>

        <div className="scheduled-commits">
          <div className="commit-list-heading">
            <div>
              <p className="policy-kicker">Timeline</p>
              <h2>Zakazani commitovi</h2>
            </div>
            <button type="button" onClick={loadCommits} disabled={isLoading}>Osvježi</button>
          </div>
          {isLoading ? (
            <p className="commit-empty">Učitavanje…</p>
          ) : commits.length === 0 ? (
            <p className="commit-empty">Još nema zakazanih commitova.</p>
          ) : (
            <div className="commit-list">
              {commits.map((commit) => (
                <article className="commit-item" key={commit.id}>
                  <div className="commit-item-top">
                    <span className={`commit-status status-${commit.status.toLowerCase()}`}>
                      {commit.status}
                    </span>
                    <span>{commit.username}</span>
                  </div>
                  <code title={commit.hash}>{commit.hash}</code>
                  <dl>
                    <div><dt>Kreiran</dt><dd>{formatDate(commit.received_at)}</dd></div>
                    <div><dt>Spreman</dt><dd>{formatDate(commit.matures_at)}</dd></div>
                  </dl>
                  {commit.status === 'READY' && revealingId !== commit.id && (
                    <button
                      className="commit-reveal-button"
                      type="button"
                      onClick={() => openReveal(commit.id)}
                    >
                      Reveal i primijeni
                    </button>
                  )}
                  {revealingId === commit.id && (
                    <form className="reveal-form" onSubmit={handleReveal}>
                      <label htmlFor={`intent-${commit.id}`}>Intent JSON</label>
                      <textarea
                        id={`intent-${commit.id}`}
                        rows={8}
                        value={intentJson}
                        onChange={(event) => setIntentJson(event.target.value)}
                        placeholder={'{\n  "domain": "example.test",\n  "operation": "ADD_RECORD",\n  ...\n}'}
                        required
                      />
                      <label htmlFor={`nonce-${commit.id}`}>Nonce</label>
                      <input
                        id={`nonce-${commit.id}`}
                        value={nonce}
                        onChange={(event) => setNonce(event.target.value)}
                        placeholder="Originalni Base64 nonce"
                        required
                      />
                      <div className="reveal-actions">
                        <button type="button" onClick={() => setRevealingId(null)}>Otkaži</button>
                        <button type="submit" disabled={isApplying}>
                          {isApplying ? 'Primjena…' : 'Primijeni promjenu'}
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
