import { useState } from 'react';

import AddDomainForm from '../components/AddDomainForm.jsx';

function DomainIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.4 2.5 3.7 5.5 3.7 9S14.4 18.5 12 21c-2.4-2.5-3.7-5.5-3.7-9S9.6 5.5 12 3Z" />
    </svg>
  );
}

export default function DomainsHome({ domains, isLoading, onSelectDomain, onCreateDomain }) {
  const [isAdding, setIsAdding] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleCreate(payload) {
    setIsSubmitting(true);
    try {
      if (await onCreateDomain(payload)) setIsAdding(false);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="page-container">
      <section className="domain-section">
        <div className="section-heading domain-section-heading">
          <h2>Your domains</h2>
          <button className="add-record-button" type="button" onClick={() => setIsAdding(true)}>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 5v14M5 12h14" />
            </svg>
            <span>Add domain</span>
          </button>
        </div>

        {isLoading ? (
          <div className="loading-state">Loading domains…</div>
        ) : domains.length === 0 ? (
          <div className="empty-state">
            You are not a member of any domain yet. Add your own domain, or ask a member of an existing domain to add you from its Members tab.
          </div>
        ) : (
          <div className="domain-list">
            {domains.map((domain) => (
              <button
                className="domain-row"
                type="button"
                key={domain.id}
                onClick={() => onSelectDomain(domain.id)}
              >
                <span className="domain-icon"><DomainIcon /></span>
                <span className="domain-primary">
                  <strong>{domain.name}</strong>
                  <small>{domain.description || 'Managed domain'}</small>
                </span>
                <span className="domain-meta">
                  <small>Registrar</small>
                  <strong>{domain.registrar || '—'}</strong>
                </span>
                <span className="domain-meta">
                  <small>DNS records</small>
                  <strong>{domain.record_count}</strong>
                </span>
                {domain.membership_status === 'PENDING' ? (
                  <span className="pending-badge" title="Waiting for a majority of members to accept you">★ Pending approval</span>
                ) : (
                  <span className="active-badge"><i /> Active</span>
                )}
                <span className="row-arrow" aria-hidden="true">→</span>
              </button>
            ))}
          </div>
        )}
      </section>

      {isAdding && (
        <AddDomainForm
          isSubmitting={isSubmitting}
          onSubmit={handleCreate}
          onClose={() => setIsAdding(false)}
        />
      )}
    </div>
  );
}
