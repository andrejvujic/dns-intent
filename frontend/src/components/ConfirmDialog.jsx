import { useEffect, useRef } from 'react';

export default function ConfirmDialog({ record, isDeleting, onConfirm, onCancel }) {
  const cancelRef = useRef(null);

  useEffect(() => {
    cancelRef.current?.focus();

    function handleKeyDown(event) {
      if (event.key === 'Escape' && !isDeleting) onCancel();
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isDeleting, onCancel]);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !isDeleting) onCancel();
    }}>
      <section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-description">
        <span className="danger-icon" aria-hidden="true">!</span>
        <h2 id="confirm-title">Delete {record.type} record?</h2>
        <p id="confirm-description">This action permanently removes the DNS record. It cannot be undone.</p>
        <div className="modal-actions">
          <button ref={cancelRef} className="button-secondary" type="button" onClick={onCancel} disabled={isDeleting}>Cancel</button>
          <button className="button-danger" type="button" onClick={onConfirm} disabled={isDeleting}>
            {isDeleting ? 'Deleting…' : 'Delete record'}
          </button>
        </div>
      </section>
    </div>
  );
}
