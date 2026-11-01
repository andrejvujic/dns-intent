import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  createDomainRecord,
  deleteDomainRecord,
  enableDnsIntent,
  getDomainMembers,
  getDomainTeam,
  getInviteCandidates,
  inviteToDomain,
  registerOwnKeys,
  updateDomainRecord,
  voteMembershipRequest,
} from '../api/domains.js';
import DirectDnsRecordManager from '../components/DirectDnsRecordManager.jsx';
import DnsIntentProtectedManager from '../components/DnsIntentProtectedManager.jsx';
import IntentEnableForm from '../components/IntentEnableForm.jsx';
import MembersPanel from '../components/MembersPanel.jsx';
import { personName } from '../utils.js';
import PendingPanicChanges from '../components/PendingPanicChanges.jsx';
import { recordContent, recordName } from '../components/DnsRecordTable.jsx';
import {
  downloadPrivateKeys,
  generateDomainKeys,
  generateMemberKeys,
  publicKeysPayload,
} from '../crypto/keys.js';

function downloadPanicChange(domainName, operation, change) {
  const blob = new Blob([`${JSON.stringify(change, null, 2)}\n`], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${domainName.replace(/[^a-z0-9.-]/gi, '_')}-${operation.toLowerCase()}-panic.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function DomainConfiguration({
  user,
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
  const [preparedPanicChange, setPreparedPanicChange] = useState(null);
  const [team, setTeam] = useState(null);
  const [isLoadingTeam, setIsLoadingTeam] = useState(false);
  const [votingId, setVotingId] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [invitingId, setInvitingId] = useState(null);
  const [isRegisteringKeys, setIsRegisteringKeys] = useState(false);
  const ieRecord = domain?.records.find((record) => record.type === 'IE');
  const dnsIntentEnabled = Boolean(ieRecord);
  const isPendingMember = domain?.membership_status === 'PENDING';
  // Pending members may edit an unprotected domain; a protected one needs approval first.
  const isReadOnly = isPendingMember && dnsIntentEnabled;
  const needsOwnKeys = dnsIntentEnabled && !isPendingMember && domain && !domain.has_intent_keys;
  const pendingRequestCount = team?.requests.length ?? 0;
  const domainId = domain?.id;

  const loadTeam = useCallback(async () => {
    if (!domainId) return;
    setIsLoadingTeam(true);
    try {
      const loadedTeam = await getDomainTeam(userId, domainId);
      setTeam(loadedTeam);
      // Only accepted members may propose new users.
      setCandidates(loadedTeam.my_status === 'ACCEPTED' ? await getInviteCandidates(userId, domainId) : []);
    } catch (teamError) {
      onNotify('error', teamError.message);
    } finally {
      setIsLoadingTeam(false);
    }
    // onNotify is recreated on every App render; reload only when the domain changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, domainId]);

  useEffect(() => {
    loadTeam();
  }, [loadTeam]);
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

  async function handleMembershipVote(request, decision) {
    setVotingId(request.membership_id);
    try {
      const updatedTeam = await voteMembershipRequest(userId, domain.id, request.membership_id, decision);
      setTeam(updatedTeam);
      const stillPending = updatedTeam.requests.some((item) => item.membership_id === request.membership_id);
      const accepted = updatedTeam.members.some(
        (member) => member.user_id === request.user_id && member.membership_status === 'ACCEPTED',
      );
      const name = personName(request);
      onNotify('success', stillPending
        ? `Your vote was recorded. ${name} still needs more votes.`
        : accepted
          ? `The quorum accepted ${name}. They can now take part in this domain.`
          : `The quorum declined ${name}'s request.`);
    } catch (voteError) {
      onNotify('error', voteError.message);
    } finally {
      setVotingId(null);
    }
  }

  async function handleInvite(candidate) {
    setInvitingId(candidate.user_id);
    try {
      const updatedTeam = await inviteToDomain(userId, domain.id, candidate.user_id);
      setTeam(updatedTeam);
      setCandidates((current) => current.filter((item) => item.user_id !== candidate.user_id));
      const name = personName(candidate);
      const accepted = updatedTeam.members.some(
        (member) => member.user_id === candidate.user_id && member.membership_status === 'ACCEPTED',
      );
      onNotify('success', accepted
        ? `${name} was added to ${domain.name}.`
        : `A vote to add ${name} was started. The members were notified by email.`);
    } catch (inviteError) {
      onNotify('error', inviteError.message);
    } finally {
      setInvitingId(null);
    }
  }

  async function handleRegisterOwnKeys() {
    setIsRegisteringKeys(true);
    try {
      const keyFile = await generateMemberKeys(domain, user);
      const [ownKeys] = publicKeysPayload(keyFile);
      await registerOwnKeys(userId, domain.id, {
        intent_public_key: ownKeys.intent_public_key,
        panic_public_key: ownKeys.panic_public_key,
      });
      downloadPrivateKeys(keyFile, 'my-private-keys');
      onNotify('success', 'Your keys were created on this device. The private-key file was downloaded; store it securely.');
      await Promise.all([onReloadDomain(), loadTeam()]);
    } catch (keysError) {
      onNotify('error', keysError.message);
    } finally {
      setIsRegisteringKeys(false);
    }
  }

  function handleDisableIntent() {
    const change = {
      type: 'PANIC_CHANGE',
      request_id: crypto.randomUUID(),
      domain: domain.name,
      operation: 'DISABLE_DNS_INTENT',
      expires_at: new Date(Date.now() + 86_400_000).toISOString(),
    };
    downloadPanicChange(domain.name, change.operation, change);

    setPreparedPanicChange(change);
    setActiveView('commits');
    onNotify('success', 'The DNS Intent shutdown panic JSON was downloaded. Sign it with your panic key, then submit it below.');
  }

  function handleRotateKeys() {
    const change = {
      type: 'PANIC_CHANGE',
      request_id: crypto.randomUUID(),
      domain: domain.name,
      operation: 'ROTATE_KEYS',
      expires_at: new Date(Date.now() + 86_400_000).toISOString(),
    };
    downloadPanicChange(domain.name, change.operation, change);
    setPreparedPanicChange(change);
    setActiveView('commits');
    onNotify('success', 'The key-rotation panic JSON was downloaded. New keys will be generated only after the quorum approves it.');
  }

  function handleRequestMemberRemoval(member) {
    const change = {
      type: 'PANIC_CHANGE',
      request_id: crypto.randomUUID(),
      domain: domain.name,
      operation: 'REMOVE_MEMBER',
      target_user_id: member.user_id,
      expires_at: new Date(Date.now() + 86_400_000).toISOString(),
    };
    downloadPanicChange(domain.name, change.operation, change);
    setPreparedPanicChange(change);
    setActiveView('commits');
    onNotify('success', `The removal request for ${personName(member)} was downloaded. Sign it with your panic key, then submit it below.`);
  }

  if (isLoading || !domain) {
    return <div className="page-container"><div className="loading-state">Loading DNS configuration…</div></div>;
  }

  return (
    <div className="page-container">
      <button className="back-button" type="button" onClick={onBack}>← All domains</button>

      <section className="page-heading domain-heading">
        <h1>{domain.name}</h1>
        <div className="domain-heading-actions">
          {dnsIntentEnabled && !isPendingMember && (
            <button className="button-secondary rotate-keys-button" type="button" onClick={handleRotateKeys}>
              Rotate keys
            </button>
          )}
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
              aria-label={dnsIntentEnabled ? 'Start DNS Intent shutdown' : 'Enable DNS Intent protection'}
              title={isPendingMember ? 'Only accepted members can change DNS Intent protection' : undefined}
              disabled={isPendingMember}
              onClick={dnsIntentEnabled ? handleDisableIntent : openIntentForm}
            >
              <span className="switch-knob" />
            </button>
          </div>
        </div>
      </section>

      {isPendingMember && (
        <div className="membership-banner is-pending" role="status">
          <span aria-hidden="true">★</span>
          <div>
            <strong>Your membership is pending approval.</strong>
            <p>
              {dnsIntentEnabled
                ? 'This domain is protected by DNS Intent, so you can only view it until a majority of its members accepts you.'
                : 'You can already edit records because this domain is not protected. Protected actions need a majority of members to accept you.'}
            </p>
          </div>
        </div>
      )}

      {needsOwnKeys && (
        <div className="membership-banner is-keys" role="status">
          <span aria-hidden="true">⚿</span>
          <div>
            <strong>Create your intent and panic keys.</strong>
            <p>You were accepted after protection was enabled. Your keys are generated on this device; only the public keys are sent to the server.</p>
          </div>
          <button className="button-primary" type="button" disabled={isRegisteringKeys} onClick={handleRegisterOwnKeys}>
            {isRegisteringKeys ? 'Generating…' : 'Generate my keys'}
          </button>
        </div>
      )}

      <nav className="domain-workspace-nav" aria-label="Domain workspace" role="tablist">
        {dnsIntentEnabled && !isPendingMember && (
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
        {dnsIntentEnabled && !isPendingMember && (
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
        <button
          className={activeView === 'members' ? 'is-active' : ''}
          type="button"
          role="tab"
          aria-selected={activeView === 'members'}
          aria-controls="members-view"
          onClick={() => setActiveView('members')}
        >
          <span>
            Members
            {pendingRequestCount > 0 && <em className="nav-count">{pendingRequestCount}</em>}
          </span>
          <small>Add users and vote on new members</small>
        </button>
      </nav>

      {activeView === 'records' && (
        <section id="dns-records-view" role="tabpanel" aria-label="DNS records">
          <DirectDnsRecordManager
            records={filteredRecords}
            query={query}
            onQueryChange={setQuery}
            protectedTypes={protectedTypes}
            isMutating={isMutating}
            readOnly={isReadOnly}
            onCreate={handleCreate}
            onUpdate={handleUpdate}
            onDelete={handleDelete}
            onNotify={onNotify}
          />
        </section>
      )}

      {activeView === 'members' && (
        <section id="members-view" role="tabpanel" aria-label="Members">
          <MembersPanel
            team={team}
            userId={userId}
            isLoading={isLoadingTeam}
            busyId={votingId}
            candidates={candidates}
            invitingId={invitingId}
            dnsIntentEnabled={dnsIntentEnabled}
            onVote={handleMembershipVote}
            onInvite={handleInvite}
            onRequestRemoval={handleRequestMemberRemoval}
            onRefresh={loadTeam}
          />
        </section>
      )}

      {dnsIntentEnabled && !isPendingMember && activeView === 'panic' && (
        <section id="panic-workflow-view" role="tabpanel" aria-label="Pending Panic Changes">
          <PendingPanicChanges
            userId={userId}
            domainId={domain.id}
            domainName={domain.name}
            onNotify={onNotify}
            onApplied={() => Promise.all([onReloadDomain(), loadTeam()])}
          />
        </section>
      )}

      {dnsIntentEnabled && !isPendingMember && activeView === 'commits' && (
        <section id="commit-workflow-view" role="tabpanel" aria-label="Commit workflow">
          <DnsIntentProtectedManager
            ieRecord={ieRecord}
            userId={userId}
            domainId={domain.id}
            domainName={domain.name}
            records={domain.records.filter((record) => record.type !== 'IE')}
            onNotify={onNotify}
            onApplied={onReloadDomain}
            onPanicSubmitted={() => {
              setPreparedPanicChange(null);
              setActiveView('panic');
            }}
            initialPanicChange={preparedPanicChange}
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
