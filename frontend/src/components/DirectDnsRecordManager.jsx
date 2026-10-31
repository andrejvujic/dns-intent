import { useMemo, useState } from 'react';

import ConfirmDialog from './ConfirmDialog.jsx';
import DnsRecordForm, { RECORD_TYPES } from './DnsRecordForm.jsx';
import DnsRecordTable from './DnsRecordTable.jsx';

export default function DirectDnsRecordManager({
  records,
  query,
  onQueryChange,
  protectedTypes = new Set(),
  isMutating,
  onCreate,
  onUpdate,
  onDelete,
  onNotify,
}) {
  const [formState, setFormState] = useState(null);
  const [recordToDelete, setRecordToDelete] = useState(null);
  const availableTypes = useMemo(
    () => RECORD_TYPES.filter((type) => !protectedTypes.has(type)),
    [protectedTypes],
  );

  async function handleFormSubmit(payload) {
    const succeeded = formState.mode === 'edit'
      ? await onUpdate(formState.record.id, payload.value)
      : await onCreate(payload);

    if (succeeded) setFormState(null);
  }

  async function handleDelete() {
    const succeeded = await onDelete(recordToDelete.id);
    if (succeeded) setRecordToDelete(null);
  }

  return (
    <section className="records-panel">
      <div className="records-toolbar">
        <h2>DNS records</h2>
        <div className="records-toolbar-actions">
          <label className="record-search">
            <span aria-hidden="true">⌕</span>
            <input
              type="search"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="Search records"
              aria-label="Search DNS records"
            />
          </label>
          <button
            className="add-record-button"
            type="button"
            onClick={() => setFormState({ mode: 'add' })}
            disabled={isMutating || availableTypes.length === 0}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 5v14M5 12h14" />
            </svg>
            <span>Add record</span>
          </button>
        </div>
      </div>

      <DnsRecordTable
        records={records}
        protectedTypes={protectedTypes}
        isBusy={isMutating}
        onEdit={(record) => setFormState({ mode: 'edit', record })}
        onDelete={setRecordToDelete}
      />

      {formState && (
        <DnsRecordForm
          mode={formState.mode}
          record={formState.record}
          availableTypes={availableTypes}
          isSubmitting={isMutating}
          onSubmit={handleFormSubmit}
          onClose={() => setFormState(null)}
          onNotify={onNotify}
        />
      )}

      {recordToDelete && (
        <ConfirmDialog
          record={recordToDelete}
          isDeleting={isMutating}
          onConfirm={handleDelete}
          onCancel={() => setRecordToDelete(null)}
        />
      )}
    </section>
  );
}
