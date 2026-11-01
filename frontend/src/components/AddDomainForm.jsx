import { useEffect, useRef, useState } from 'react';

const DOMAIN_PATTERN = /^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$/;

export default function AddDomainForm({ isSubmitting, onSubmit, onClose }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [registrar, setRegistrar] = useState('');
  const firstInputRef = useRef(null);
  const normalizedName = name.trim().toLowerCase().replace(/\.$/, '');
  const nameValid = DOMAIN_PATTERN.test(normalizedName);

  useEffect(() => {
    firstInputRef.current?.focus();

    function handleKeyDown(event) {
      if (event.key === 'Escape' && !isSubmitting) onClose();
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isSubmitting, onClose]);

  function handleSubmit(event) {
    event.preventDefault();
    if (!nameValid || isSubmitting) return;
    onSubmit({
      name: normalizedName,
      description: description.trim() || null,
      registrar: registrar.trim() || null,
    });
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !isSubmitting) onClose();
    }}>
      <section className="record-modal" role="dialog" aria-modal="true" aria-labelledby="add-domain-title">
        <header className="modal-header">
          <div>
            <p className="modal-kicker">New domain</p>
            <h2 id="add-domain-title">Add a domain</h2>
          </div>
          <button className="modal-close" type="button" onClick={onClose} disabled={isSubmitting} aria-label="Close form">×</button>
        </header>

        <form className="record-form" onSubmit={handleSubmit} noValidate>
          <p className="form-hint add-domain-hint">
            You become the domain's first member. You can enable DNS Intent right away and add other users later; each addition is decided by a majority vote.
          </p>
          <div className="form-grid">
            <label className="form-field form-field-wide">
              <span>Domain name</span>
              <input
                ref={firstInputRef}
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="example.com"
                aria-invalid={name.length > 0 && !nameValid}
                disabled={isSubmitting}
                required
              />
            </label>
            {name.length > 0 && !nameValid && (
              <p className="field-hint is-error form-field-wide">Use a domain name such as example.com (letters, numbers and hyphens).</p>
            )}
            <label className="form-field form-field-wide">
              <span>Description (optional)</span>
              <input value={description} onChange={(event) => setDescription(event.target.value)} disabled={isSubmitting} />
            </label>
            <label className="form-field form-field-wide">
              <span>Registrar (optional)</span>
              <input value={registrar} onChange={(event) => setRegistrar(event.target.value)} disabled={isSubmitting} />
            </label>
          </div>

          <footer className="modal-actions">
            <button className="button-secondary" type="button" onClick={onClose} disabled={isSubmitting}>Cancel</button>
            <button className="button-primary" type="submit" disabled={!nameValid || isSubmitting}>
              {isSubmitting ? 'Adding…' : 'Add domain'}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
