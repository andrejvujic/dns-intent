import { useMemo, useState } from 'react';

import {
  createDomainRecord,
  deleteDomainRecord,
  enableDnsIntent,
  getDomainMembers,
  updateDomainRecord,
} from '../api/domains.js';
import DirectDnsRecordManager from '../components/DirectDnsRecordManager.jsx';
import DnsIntentProtectedManager from '../components/DnsIntentProtectedManager.jsx';
import IntentEnableForm from '../components/IntentEnableForm.jsx';
import PendingPanicChanges from '../components/PendingPanicChanges.jsx';
import { recordContent, recordName } from '../components/DnsRecordTable.jsx';
import {
  downloadPrivateKeys,
  generateDomainKeys,
  publicKeysPayload,
} from '../crypto/keys.js';

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
  const [isEnablingIntent, setIsEnablingIntent] = useState(false);
  const [members, setMembers] = useState([]);
  const [isLoadingMembers, setIsLoadingMembers] = useState(false);
  const [isSubmittingIntent, setIsSubmittingIntent] = useState(false);
  const [activeView, setActiveView] = useState('records');
  const ieRecord = domain?.records.find((record) => record.type === 'IE');
  const dnsIntentEnabled = Boolean(ieRecord);
  const protectedTypes = useMemo(() => {
    const operations = ieRecord?.value?.protected_operations;
    if (!Array.isArray(operations)) return new Set();
    return new Set(operations.map((type) => type.toUpperCase()));
  }, [ieRecord]);

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

  async function openIntentForm() {
    if (dnsIntentEnabled || isEnablingIntent) return;
    setIsEnablingIntent(true);
    setIsLoadingMembers(true);

    try {
      setMembers(await getDomainMembers(userId, domain.id));
    } catch (membersError) {
      onNotify('error', membersError.message);
      setIsEnablingIntent(false);
    } finally {
      setIsLoadingMembers(false);
    }
  }

  async function handleEnableIntent(payload) {
    setIsSubmittingIntent(true);

    try {
      const keyFile = await generateDomainKeys(domain, members);
      await enableDnsIntent(userId, domain.id, {
        ...payload,
        public_keys: publicKeysPayload(keyFile),
      });
      downloadPrivateKeys(keyFile);
      onNotify('success', 'DNS Intent was enabled. The private-key file was downloaded; store it securely.');
      setIsEnablingIntent(false);
      onReloadDomain().catch((reloadError) => {
        onNotify('error', `Protection was enabled, but refresh failed: ${reloadError.message}`);
      });
    } catch (requestError) {
      onNotify('error', requestError.message);
    } finally {
      setIsSubmittingIntent(false);
    }
  }

  if (isLoading || !domain) {
    return <div className="page-container"><div className="loading-state">Loading DNS configuration…</div></div>;
  }

  return (
    <div className="page-container">
      <button className="back-button" type="button" onClick={onBack}>← All domains</button>

      <section className="page-heading domain-heading">
        <h1>{domain.name}</h1>
        <div className="intent-toggle">
          <div className="intent-toggle-copy">
            <strong>DNS Intent</strong>
            <span>{dnsIntentEnabled ? 'Protected' : 'Standard'}</span>
          </div>
          <button
            className={`switch${dnsIntentEnabled ? ' is-on' : ''}`}
            type="button"
            role="switch"
            aria-checked={dnsIntentEnabled}
            aria-label={dnsIntentEnabled ? 'DNS Intent is enabled' : 'Enable DNS Intent protection'}
            onClick={openIntentForm}
            disabled={dnsIntentEnabled}
          >
            <span className="switch-knob" />
          </button>
        </div>
      </section>

      <nav className="domain-workspace-nav" aria-label="Domain workspace" role="tablist">
        {dnsIntentEnabled && (
          <button
            className={activeView === 'panic' ? 'is-active' : ''}
            type="button" role="tab" aria-selected={activeView === 'panic'}
            aria-controls="panic-workflow-view" onClick={() => setActiveView('panic')}
          >
            <span>Pending Panic Changes</span>
            <small>Review, sign, accept, or reject</small>
          </button>
        )}
        <button
          className={activeView === 'records' ? 'is-active' : ''}
          type="button"
          role="tab"
          aria-selected={activeView === 'records'}
          aria-controls="dns-records-view"
          onClick={() => setActiveView('records')}
        >
          <span>DNS records</span>
          <small>View and manage domain data</small>
        </button>
        {dnsIntentEnabled && (
          <button
            className={activeView === 'commits' ? 'is-active' : ''}
            type="button"
            role="tab"
            aria-selected={activeView === 'commits'}
            aria-controls="commit-workflow-view"
            onClick={() => setActiveView('commits')}
          >
            <span>Commit workflow</span>
            <small>Prepare, schedule, and reveal changes</small>
          </button>
        )}
      </nav>

      {activeView === 'records' && (
        <section id="dns-records-view" role="tabpanel" aria-label="DNS records">
          <DirectDnsRecordManager
            records={filteredRecords}
            query={query}
            onQueryChange={setQuery}
            protectedTypes={protectedTypes}
            isMutating={isMutating}
            onCreate={handleCreate}
            onUpdate={handleUpdate}
            onDelete={handleDelete}
            onNotify={onNotify}
          />
        </section>
      )}

      {dnsIntentEnabled && activeView === 'panic' && (
        <section id="panic-workflow-view" role="tabpanel" aria-label="Pending Panic Changes">
          <PendingPanicChanges userId={userId} domainId={domain.id} onNotify={onNotify} onApplied={onReloadDomain} />
        </section>
      )}

      {dnsIntentEnabled && activeView === 'commits' && (
        <section id="commit-workflow-view" role="tabpanel" aria-label="Commit workflow">
          <DnsIntentProtectedManager
            ieRecord={ieRecord}
            userId={userId}
            domainId={domain.id}
            domainName={domain.name}
            records={domain.records.filter((record) => record.type !== 'IE')}
            onNotify={onNotify}
            onApplied={onReloadDomain}
          />
        </section>
      )}

      {isEnablingIntent && (
        <IntentEnableForm
          domain={domain}
          members={members}
          isLoadingMembers={isLoadingMembers}
          isSubmitting={isSubmittingIntent}
          onSubmit={handleEnableIntent}
          onClose={() => setIsEnablingIntent(false)}
          onNotify={onNotify}
        />
      )}
    </div>
  );
}
