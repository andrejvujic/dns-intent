import { personInitials, personName } from '../utils.js';
export default function AppHeader({ user, onHome, onLogout }) {
  const initials = personInitials(user);

  return (
    <header className="app-header">
      <button className="header-brand" type="button" onClick={onHome} aria-label="Home">
        DI
      </button>
      <nav className="header-nav" aria-label="Primary navigation">
        <button type="button" onClick={onHome}>Domains</button>
      </nav>
      <div className="account-menu">
        <div className="account-copy">
          <strong>{personName(user)}</strong>
          <span>{user.email}</span>
        </div>
        <span className="avatar" aria-hidden="true">{initials}</span>
        <button className="logout-button" type="button" onClick={onLogout}>Log out</button>
      </div>
    </header>
  );
}
