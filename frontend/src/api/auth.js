function detailMessage(detail, fallback) {
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.filter((part) => part !== 'body').join('.') : '';
        const message = String(item.msg || 'Invalid value').replace(/^Value error, /, '');
        return field ? `${field}: ${message}` : message;
      })
      .join(' • ');
  }
  return detail || fallback;
}

export async function registerUser(payload) {
  const response = await fetch('/api/auth/register', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(detailMessage(data?.detail, 'Registration is currently unavailable.'));
  }

  return data;
}

export async function getPublicDomains() {
  const response = await fetch('/api/auth/domains');
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(detailMessage(data?.detail, 'Domains could not be loaded.'));
  }

  return data;
}

export async function loginUser(email, password) {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email, password }),
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(data?.detail || 'Login is currently unavailable.');
  }

  return data;
}
