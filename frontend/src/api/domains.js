async function getJson(url) {
  const response = await fetch(url);
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(data?.detail || 'Domain data is currently unavailable.');
  }

  return data;
}

export function getUserDomains(userId) {
  return getJson(`/api/users/${userId}/domains`);
}

export function getUserDomain(userId, domainId) {
  return getJson(`/api/users/${userId}/domains/${domainId}`);
}
