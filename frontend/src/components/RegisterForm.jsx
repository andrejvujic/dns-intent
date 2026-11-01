import { useMemo, useState } from 'react';

import { registerUser } from '../api/auth.js';

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;

// Same rules the backend enforces in app/core/security.py.
export const PASSWORD_RULES = [
  { id: 'length', label: 'At least 10 characters', test: (value) => value.length >= 10 },
  { id: 'upper', label: 'One uppercase letter (A–Z)', test: (value) => /[A-Z]/.test(value) },
  { id: 'lower', label: 'One lowercase letter (a–z)', test: (value) => /[a-z]/.test(value) },
  { id: 'number', label: 'One number (0–9)', test: (value) => /[0-9]/.test(value) },
  { id: 'special', label: 'One special character (!@#$…)', test: (value) => /[^A-Za-z0-9\s]/.test(value) },
  { id: 'spaces', label: 'No spaces', test: (value) => value.length > 0 && !/\s/.test(value) },
];

const STRENGTH_LABELS = ['Too weak', 'Weak', 'Fair', 'Good', 'Strong'];

function EyeIcon({ open }) {
  return open ? (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m3 3 18 18M10.6 10.7a2 2 0 0 0 2.7 2.7M9.9 4.2A10.8 10.8 0 0 1 12 4c5.5 0 9 5 9 5a15.7 15.7 0 0 1-2.1 2.5M6.6 6.6C4.4 8.1 3 10 3 10s3.5 5 9 5a10.7 10.7 0 0 0 3.4-.5" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 12s3.5-5 9-5 9 5 9 5-3.5 5-9 5-9-5-9-5Z" />
      <circle cx="12" cy="12" r="2.5" />
    </svg>
  );
}

export default function RegisterForm({ onRegistered, onShowLogin, onNotify }) {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const ruleResults = useMemo(
    () => PASSWORD_RULES.map((rule) => ({ ...rule, passed: rule.test(password) })),
    [password],
  );
  const passedCount = ruleResults.filter((rule) => rule.passed).length;
  const passwordValid = passedCount === ruleResults.length;
  const lengthMet = ruleResults[0].passed;
  // A short password is never better than "Weak", whatever else it contains.
  const strength = !password ? 0
    : passwordValid ? 4
      : Math.min(lengthMet ? 3 : 1, Math.floor((passedCount / ruleResults.length) * 4));
  const emailValid = EMAIL_PATTERN.test(email.trim());
  const passwordsMatch = confirm.length > 0 && confirm === password;
  const canSubmit = firstName.trim() && lastName.trim() && emailValid && passwordValid && passwordsMatch
    && !isSubmitting;

  async function handleSubmit(event) {
    event.preventDefault();
    if (!canSubmit) return;
    setIsSubmitting(true);

    try {
      const data = await registerUser({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        password,
      });
      onRegistered(data);
    } catch (registerError) {
      onNotify('error', registerError.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="auth-card register-card" onSubmit={handleSubmit} noValidate>
      <h2>Create an account</h2>
      <p className="form-intro">
        Your email is your username. After signing up, add your own domain or wait for a domain's members to add you.
      </p>

      <div className="register-name-row">
        <div>
          <label htmlFor="first_name">First name</label>
          <input id="first_name" autoComplete="given-name" value={firstName} onChange={(event) => setFirstName(event.target.value)} required />
        </div>
        <div>
          <label htmlFor="last_name">Last name</label>
          <input id="last_name" autoComplete="family-name" value={lastName} onChange={(event) => setLastName(event.target.value)} required />
        </div>
      </div>

      <label htmlFor="register-email">Email</label>
      <input
        id="register-email"
        type="email"
        autoComplete="username"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        aria-invalid={email.length > 0 && !emailValid}
        required
      />
      {email.length > 0 && !emailValid && <p className="field-hint is-error">Enter a valid email address.</p>}

      <label htmlFor="register-password">Password</label>
      <div className="password-field">
        <input
          id="register-password"
          type={showPassword ? 'text' : 'password'}
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          aria-describedby="password-rules"
          required
        />
        <button
          className="password-toggle"
          type="button"
          onClick={() => setShowPassword((isVisible) => !isVisible)}
          aria-label={showPassword ? 'Hide password' : 'Show password'}
          aria-pressed={showPassword}
        >
          <EyeIcon open={showPassword} />
        </button>
      </div>

      <div className={`password-strength strength-${strength}`} aria-hidden={!password}>
        <div className="password-strength-bar"><span style={{ width: `${(strength / 4) * 100}%` }} /></div>
        <small>{password ? STRENGTH_LABELS[strength] : 'Password strength'}</small>
      </div>

      <ul className="password-rules" id="password-rules" aria-live="polite">
        {ruleResults.map((rule) => (
          <li key={rule.id} className={rule.passed ? 'is-met' : ''}>
            <span aria-hidden="true">{rule.passed ? '✓' : '○'}</span>
            {rule.label}
            <span className="visually-hidden">{rule.passed ? ' – met' : ' – not met'}</span>
          </li>
        ))}
      </ul>

      <label htmlFor="register-confirm">Confirm password</label>
      <input
        id="register-confirm"
        type={showPassword ? 'text' : 'password'}
        autoComplete="new-password"
        value={confirm}
        onChange={(event) => setConfirm(event.target.value)}
        aria-invalid={confirm.length > 0 && !passwordsMatch}
        required
      />
      {confirm.length > 0 && (
        <p className={`field-hint${passwordsMatch ? ' is-ok' : ' is-error'}`}>
          {passwordsMatch ? 'Passwords match.' : 'Passwords do not match.'}
        </p>
      )}

      <button className="primary-button" type="submit" disabled={!canSubmit}>
        {isSubmitting ? 'Creating account…' : 'Create account'}
      </button>

      <p className="auth-switch">
        Already have an account?{' '}
        <button className="link-button" type="button" onClick={onShowLogin}>Sign in</button>
      </p>
    </form>
  );
}
