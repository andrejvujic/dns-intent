function validationErrorMessage(error) {
  if (typeof error === 'string') return error;
  if (!error || typeof error !== 'object') return 'Request could not be completed.';

  const location = Array.isArray(error.loc)
    ? error.loc.filter((part) => part !== 'body').join('.')
    : '';
  const message = error.msg || 'Invalid value';
  return location ? `${location}: ${message}` : message;
}

function errorMessage(detail) {
  if (Array.isArray(detail)) {
    return detail.map(validationErrorMessage).join(' • ');
  }

  return validationErrorMessage(detail);
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = response.status === 204
    ? null
    : await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(
      data?.detail
        ? errorMessage(data.detail)
        : 'Domain request could not be completed.',
      response.status,
    );
  }

  return data;
}

export function getUserDomains(userId) {
  return requestJson(`/api/users/${userId}/domains`);
}

export function getUserDomain(userId, domainId) {
  return requestJson(`/api/users/${userId}/domains/${domainId}`);
}

export function getDomainMembers(userId, domainId) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/members`);
}

export function getDomainTeam(userId, domainId) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/team`);
}

export function voteMembershipRequest(userId, domainId, membershipId, decision) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/membership-requests/${membershipId}/vote`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision }),
  });
}

export function registerOwnKeys(userId, domainId, publicKeys) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/my-keys`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(publicKeys),
  });
}

export function createDomain(userId, payload) {
  return requestJson(`/api/users/${userId}/domains`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
}

export function getInviteCandidates(userId, domainId) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/candidates`);
}

export function inviteToDomain(userId, domainId, inviteeId) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/invitations`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: inviteeId }),
  });
}

export function enableDnsIntent(userId, domainId, payload) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/intent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function scheduleCommit(userId, domainId, payload) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/commits`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getScheduledCommits(userId, domainId) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/commits`);
}

export function revealCommit(userId, domainId, commitId, payload) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/commits/${commitId}/reveal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function createPanicChange(userId, domainId, payload) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/panic-changes`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
}

export function getPanicChanges(userId, domainId) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/panic-changes`);
}

export function attachPanicSignature(userId, domainId, panicId, signature) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/panic-changes/${panicId}/signatures`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ signature }),
  });
}

export function votePanicChange(userId, domainId, panicId, decision, signature) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/panic-changes/${panicId}/vote`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, signature }),
  });
}

export function finalizeKeyRotation(userId, domainId, panicId, publicKeys) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/panic-changes/${panicId}/rotation-keys`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ public_keys: publicKeys }),
  });
}

export function finalizeMemberRemoval(userId, domainId, panicId) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/panic-changes/${panicId}/remove-member`, {
    method: 'POST',
  });
}

export function createDomainRecord(userId, domainId, payload) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/records`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function updateDomainRecord(userId, domainId, recordId, payload) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/records/${recordId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function deleteDomainRecord(userId, domainId, recordId) {
  return requestJson(`/api/users/${userId}/domains/${domainId}/records/${recordId}`, {
    method: 'DELETE',
  });
}
