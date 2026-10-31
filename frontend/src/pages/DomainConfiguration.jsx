import { useMemo, useState } from 'react';

import {
  createDomainRecord,
  deleteDomainRecord,
  updateDomainRecord,
} from '../api/domains.js';
import DirectDnsRecordManager from '../components/DirectDnsRecordManager.jsx';
import DnsIntentProtectedManager from '../components/DnsIntentProtectedManager.jsx';
import { recordContent, recordName } from '../components/DnsRecordTable.jsx';

export default function DomainConfiguration({
  userId,
  domain,
  isLoading,
  onBack,
  onReloadDomain,
  onNotify,
}) {
  const [query, setQuery] = useState('');
  const [isMutating, setIsMutating] = useState(false);
  const ieRecord = domain?.records.find((record) => record.type === 'IE');
  const dnsIntentEnabled = Boolean(ieRecord);

  const filteredRecords = useMemo(() => {
    const records = (domain?.records || []).filter((record) => record.type !== 'IE');
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return records;

    return records.filter((record) => (
      `${record.type} ${recordName(record)} ${recordContent(record)}`
        .toLowerCase()
        .includes(normalizedQuery)
    ));
  }, [domain, query]);

  async function runMutation(request, successMessage) {
    setIsMutating(true);

    try {
      await request();
      onNotify('success', successMessage);
      onReloadDomain().catch((reloadError) => {
        onNotify('error', `The change was saved, but refresh failed: ${reloadError.message}`);
      });
      return true;
    } catch (requestError) {
      onNotify('error', requestError.message);

      if (requestError.status === 409) {
        try {
          await onReloadDomain();
        } catch (reloadError) {
          onNotify('error', `${requestError.message} ${reloadError.message}`);
        }
      }

      return false;
    } finally {
      setIsMutating(false);
    }
  }

  function handleCreate(payload) {
    return runMutation(
      () => createDomainRecord(userId, domain.id, payload),
      'DNS record was added successfully.',
    );
  }

  function handleUpdate(recordId, value) {
    return runMutation(
      () => updateDomainRecord(userId, domain.id, recordId, { value }),
      'DNS record was updated successfully.',
    );
  }

  function handleDelete(recordId) {
    return runMutation(
      () => deleteDomainRecord(userId, domain.id, recordId),
      'DNS record was deleted successfully.',
    );
  }

  if (isLoading || !domain) {
    return <div className="page-container"><div className="loading-state">Loading DNS configuration…</div></div>;
  }

  return (
    <div className="page-container">
      <button className="back-button" type="button" onClick={onBack}>← All domains</button>

      <section className="page-heading domain-heading">
        <h1>{domain.name}</h1>
      </section>

      {dnsIntentEnabled ? (
        <DnsIntentProtectedManager
          ieRecord={ieRecord}
          records={filteredRecords}
          query={query}
          onQueryChange={setQuery}
        />
      ) : (
        <DirectDnsRecordManager
          records={filteredRecords}
          query={query}
          onQueryChange={setQuery}
          isMutating={isMutating}
          onCreate={handleCreate}
          onUpdate={handleUpdate}
          onDelete={handleDelete}
          onNotify={onNotify}
        />
      )}
    </div>
  );
}
