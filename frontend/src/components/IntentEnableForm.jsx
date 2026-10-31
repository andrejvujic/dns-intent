import { useEffect, useRef, useState } from 'react';

import { RECORD_TYPES } from './DnsRecordForm.jsx';

const DEFAULT_PROTECTED_OPERATIONS = ['NS', 'DS', 'DNSKEY'];

function memberName(member) {
  return `${member.first_name} ${member.last_name}`;
}

export default function IntentEnableForm({
  domain,
  members,
  isLoadingMembers,
  isSubmitting,
  onSubmit,
  onClose,
  onNotify,
}) {
  const [delay, setDelay] = useState('');
  const [quorum, setQuorum] = useState(() => String(Math.ceil(members.length / 2)));
  const [protectedOperations, setProtectedOperations] = useState(DEFAULT_PROTECTED_OPERATIONS);
  const firstInputRef = useRef(null);

  useEffect(() => {
    if (!isLoadingMembers) {
      setQuorum(String(Math.ceil(members.length / 2)));
    }
  }, [isLoadingMembers, members.length]);

  useEffect(() => {
    firstInputRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    function handleKeyDown(event) {
      if (event.key === 'Escape' && !isSubmitting) onClose();
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [isSubmitting, onClose]);

  function toggleOperation(type) {
    setProtectedOperations((current) => (
      current.includes(type)
        ? current.filter((item) => item !== type)
        : [...current, type]
    ));
  }

  function toggleAllOperations() {
    setProtectedOperations((current) => (
      current.length === RECORD_TYPES.length ? [] : [...RECORD_TYPES]
    ));
  }

  function handleSubmit(event) {
    event.preventDefault();

    const delayValue = Number(delay);
    if (!Number.isInteger(delayValue) || delayValue < 30) {
      onNotify('error', 'Minimal delay must be at least 30 seconds.');
      return;
    }

    const quorumValue = Number(quorum);
    if (!Number.isInteger(quorumValue) || quorumValue < 1) {
      onNotify('error', 'Panic quorum must be a whole number of at least 1.');
      return;
    }

    if (quorumValue < Math.ceil(members.length / 2)) {
      onNotify('error', `Panic quorum must be at least ${Math.ceil(members.length / 2)} for ${members.length} domain members.`);
      return;
    }

    if (protectedOperations.length === 0) {
      onNotify('error', 'Select at least one protected record type.');
      return;
    }

    onSubmit({
      panic_quorum: quorumValue,
      delay_seconds: delayValue,
      protected_operations: protectedOperations,
    });
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !isSubmitting) onClose();
    }}>
      <section className="record-modal intent-modal" role="dialog" aria-modal="true" aria-labelledby="intent-form-title">
        <header className="modal-header">
          <div>
            <p className="modal-kicker">DNS Intent</p>
            <h2 id="intent-form-title">Enable DNS Intent protection</h2>
          </div>
          <button className="modal-close" type="button" onClick={onClose} disabled={isSubmitting} aria-label="Close form">×</button>
        </header>

        <form className="record-form" onSubmit={handleSubmit} noValidate>
          <p className="form-hint">
            Turning on DNS Intent applies the commit/reveal flow to critical DNS changes on <strong>{domain.name}</strong>.
          </p>

          <div className="form-grid">
            <label className="form-field">
              <span>Minimal delay (seconds)</span>
              <input
                ref={firstInputRef}
                type="number"
                min="30"
                step="1"
                value={delay}
                onChange={(event) => setDelay(event.target.value)}
                disabled={isSubmitting}
                placeholder="e.g. 30"
                required
              />
            </label>

            <label className="form-field">
              <span>Panic quorum</span>
              <input
                type="number"
                min="1"
                step="1"
                value={quorum}
                onChange={(event) => setQuorum(event.target.value)}
                disabled={isSubmitting}
                required
              />
            </label>
          </div>

          <div className="intent-form-section">
            <div className="protected-types-header">
              <span className="form-field-label">Protected records</span>
              <button
                className="link-button"
                type="button"
                onClick={toggleAllOperations}
                disabled={isSubmitting}
              >
                {protectedOperations.length === RECORD_TYPES.length ? 'Deselect all' : 'Select all'}
              </button>
            </div>
            <p className="form-hint">Records selected here require intent authorization before they can change.</p>
            <div className="protected-types">
              {RECORD_TYPES.map((type) => {
                const isSelected = protectedOperations.includes(type);
                return (
                  <button
                    type="button"
                    className={`protected-type-option${isSelected ? ' is-selected' : ''}`}
                    key={type}
                    onClick={() => toggleOperation(type)}
                    disabled={isSubmitting}
                    aria-pressed={isSelected}
                  >
                    <span className="protected-type-check" aria-hidden="true">{isSelected ? '✓' : ''}</span>
                    {type}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="intent-form-section">
            <span className="form-field-label">Automatic key generation</span>
            <p className="form-hint">
              Enabling protection generates an Ed25519 intent and panic key pair for every domain member. Only public keys are sent to the server. A JSON file containing the private keys will download automatically.
            </p>

            {isLoadingMembers ? (
              <div className="loading-state">Loading domain members…</div>
            ) : members.length === 0 ? (
              <div className="empty-state">No members are assigned to this domain.</div>
            ) : (
              <div className="member-list">
                {members.map((member) => {
                  return (
                    <div className="member-row" key={member.id}>
                      <span className="member-name">{memberName(member)}</span>
                      <span className="form-hint">Intent + panic key pair</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <footer className="modal-actions">
            <button className="button-secondary" type="button" onClick={onClose} disabled={isSubmitting}>Cancel</button>
            <button className="button-primary" type="submit" disabled={isSubmitting || isLoadingMembers}>
              {isSubmitting ? 'Enabling…' : 'Enable protection'}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
