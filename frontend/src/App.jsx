import { useEffect, useState } from 'react';

import { loginUser } from './api/auth.js';
import { createDomain, getUserDomain, getUserDomains } from './api/domains.js';
import AppHeader from './components/AppHeader.jsx';
import RegisterForm from './components/RegisterForm.jsx';
import DomainConfiguration from './pages/DomainConfiguration.jsx';
import DomainsHome from './pages/DomainsHome.jsx';
import './styles.css';

function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem('dnsintent-user'));
  } catch {
    localStorage.removeItem('dnsintent-user');
    return null;
  }
}

function App() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [user, setUser] = useState(getStoredUser);
  const [notification, setNotification] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [domains, setDomains] = useState([]);
  const [isLoadingDomains, setIsLoadingDomains] = useState(false);
  const [selectedDomain, setSelectedDomain] = useState(null);
  const [isLoadingDomain, setIsLoadingDomain] = useState(false);
  const [authMode, setAuthMode] = useState('login');

  useEffect(() => {
    if (!notification) {
      return undefined;
    }

    const timeoutId = window.setTimeout(() => setNotification(null), 4500);
    return () => window.clearTimeout(timeoutId);
  }, [notification]);

  useEffect(() => {
    if (!user) {
      setDomains([]);
      return undefined;
    }

    let ignoreResult = false;
    setIsLoadingDomains(true);

    getUserDomains(user.id)
      .then((userDomains) => {
        if (!ignoreResult) setDomains(userDomains);
      })
      .catch((loadError) => {
        if (!ignoreResult) notify('error', loadError.message);
      })
      .finally(() => {
        if (!ignoreResult) setIsLoadingDomains(false);
      });

    return () => {
      ignoreResult = true;
    };
  }, [user]);

  async function handleSubmit(event) {
    event.preventDefault();
    setNotification(null);
    setIsSubmitting(true);

    try {
      const data = await loginUser(email, password);
      localStorage.setItem('dnsintent-user', JSON.stringify(data.user));
      setUser(data.user);
    } catch (loginError) {
      notify('error', loginError.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleRegistered(data) {
    localStorage.setItem('dnsintent-user', JSON.stringify(data.user));
    setUser(data.user);
    setAuthMode('login');
    notify('success', data.message);
  }

  async function handleCreateDomain(payload) {
    try {
      const summary = await createDomain(user.id, payload);
      setDomains((current) => [...current, summary].sort((a, b) => a.name.localeCompare(b.name)));
      notify('success', `${summary.name} was added. You are its first member.`);
      return true;
    } catch (createError) {
      notify('error', createError.message);
      return false;
    }
  }

  function handleLogout() {
    localStorage.removeItem('dnsintent-user');
    setSelectedDomain(null);
    setUser(null);
  }

  async function handleSelectDomain(domainId) {
    setNotification(null);
    setIsLoadingDomain(true);

    try {
      const domain = await getUserDomain(user.id, domainId);
      setSelectedDomain(domain);
    } catch (loadError) {
      notify('error', loadError.message);
    } finally {
      setIsLoadingDomain(false);
    }
  }

  function notify(type, message) {
    setNotification({
      type,
      title: type === 'success' ? 'Success' : 'Something went wrong',
      message,
    });
  }

  async function reloadSelectedDomain() {
    if (!user || !selectedDomain) return null;

    const updatedDomain = await getUserDomain(user.id, selectedDomain.id);
    setSelectedDomain(updatedDomain);
    setDomains((currentDomains) => currentDomains.map((domain) => (
      domain.id === updatedDomain.id
        ? {
            ...domain,
            record_count: updatedDomain.record_count,
            updated_at: updatedDomain.updated_at,
          }
        : domain
    )));
    return updatedDomain;
  }

  return (
    <main className={user ? 'portal-shell' : 'app-shell'}>
      {user ? (
        <>
          <AppHeader
            user={user}
            onHome={() => setSelectedDomain(null)}
            onLogout={handleLogout}
          />
          {selectedDomain || isLoadingDomain ? (
            <DomainConfiguration
              user={user}
              userId={user.id}
              domain={selectedDomain}
              isLoading={isLoadingDomain}
              onBack={() => setSelectedDomain(null)}
              onReloadDomain={reloadSelectedDomain}
              onNotify={notify}
            />
          ) : (
            <DomainsHome
              domains={domains}
              isLoading={isLoadingDomains}
              onSelectDomain={handleSelectDomain}
              onCreateDomain={handleCreateDomain}
            />
          )}
        </>
      ) : (
        <>
          <section className="brand-panel">
            <div className="brand-mark" aria-hidden="true">DI</div>
            <h1>Critical DNS changes, authorized in advance.</h1>
          </section>

          <section className="auth-panel">
          {authMode === 'register' ? (
            <RegisterForm
              onRegistered={handleRegistered}
              onShowLogin={() => setAuthMode('login')}
              onNotify={notify}
            />
          ) : (
          <form className="auth-card" onSubmit={handleSubmit}>
            <h2>Welcome back</h2>
            <p className="form-intro">Sign in to manage protected domains.</p>

            <label htmlFor="email">Email address</label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />

            <label htmlFor="password">Password</label>
            <div className="password-field">
              <input
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
              <button
                className="password-toggle"
                type="button"
                onClick={() => setShowPassword((isVisible) => !isVisible)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                aria-pressed={showPassword}
              >
                {showPassword ? (
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="m3 3 18 18M10.6 10.7a2 2 0 0 0 2.7 2.7M9.9 4.2A10.8 10.8 0 0 1 12 4c5.5 0 9 5 9 5a15.7 15.7 0 0 1-2.1 2.5M6.6 6.6C4.4 8.1 3 10 3 10s3.5 5 9 5a10.7 10.7 0 0 0 3.4-.5" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M3 12s3.5-5 9-5 9 5 9 5-3.5 5-9 5-9-5-9-5Z" />
                    <circle cx="12" cy="12" r="2.5" />
                  </svg>
                )}
              </button>
            </div>

            <button className="primary-button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Signing in…' : 'Sign in'}
            </button>

            <p className="auth-switch">
              Don't have an account?{' '}
              <button className="link-button" type="button" onClick={() => setAuthMode('register')}>Create one</button>
            </p>
          </form>
          )}
          </section>
        </>
      )}

      {notification && (
        <div
          className={`toast toast-${notification.type}`}
          role={notification.type === 'error' ? 'alert' : 'status'}
          aria-live={notification.type === 'error' ? 'assertive' : 'polite'}
        >
          <span className="toast-icon" aria-hidden="true">{notification.type === 'success' ? '✓' : '!'}</span>
          <div className="toast-content">
            <strong>{notification.title}</strong>
            <p>{notification.message}</p>
          </div>
          <button
            className="toast-close"
            type="button"
            onClick={() => setNotification(null)}
            aria-label="Close notification"
          >
            ×
          </button>
        </div>
      )}
    </main>
  );
}

export default App;
