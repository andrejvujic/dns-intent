import { useCallback, useEffect, useState } from 'react';

import { getScheduledCommits, scheduleCommit } from '../api/domains.js';

function policyValue(value, fallback = 'Not configured') {
  return value === undefined || value === null || value === '' ? fallback : value;
}

function formatDate(value) {
  return new Intl.DateTimeFormat('sr-Latn-RS', {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(value));
}

export default function DnsIntentProtectedManager({ ieRecord, userId, domainId, onNotify }) {
  const policy = ieRecord.value || {};
  const [hash, setHash] = useState('');
  const [signature, setSignature] = useState('');
  const [commits, setCommits] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
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
                </article>
              ))}
            </div>
          )}
        </div>
      </section>
    </>
  );
}
