import { personName } from '../utils.js';

function fullName(person) {
  return personName(person);
}

function formatDate(value) {
  // SQLite returns UTC timestamps without a zone suffix.
  const utcValue = /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  return new Date(utcValue).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export default function MembersPanel({
  team,
  userId,
  isLoading,
  candidates = [],
  candidateQuery,
  onCandidateQueryChange,
  isSearchingCandidates,
  invitingId,
  dnsIntentEnabled,
  onInvite,
  onReviewInvitations,
  onRefresh,
}) {
  if (isLoading && !team) {
    return <div className="loading-state">Loading members…</div>;
  }
  if (!team) return null;

  const canVote = team.my_status === 'ACCEPTED';

  return (
    <section className="scheduled-commits members-board">
      <div className="commit-list-heading">
        <div>
          <p className="policy-kicker">Membership quorum</p>
          <h2>Members</h2>
        </div>
        <button type="button" onClick={onRefresh} disabled={isLoading}>Refresh</button>
      </div>
      <p className="commit-help">
        {dnsIntentEnabled
          ? `Invitations use the panic signing flow and require ${team.required_quorum} signed ACCEPT votes. After approval, the inviter applies the addition in Pending Panic Changes.`
          : 'Inviting a registered user adds them to this domain immediately.'}
      </p>

      <h3 className="members-subheading">Invitations awaiting votes or application</h3>
      {team.requests.length === 0 ? (
        <p className="commit-empty">No invitations are awaiting approval or application.</p>
      ) : (
        <div className="commit-list">
          {team.requests.map((request) => {
            const isMe = request.user_id === userId;
            return (
              <article className="commit-item membership-request" key={request.membership_id}>
                <div className="commit-item-top">
                  <span className={`commit-status ${request.status === 'QUORUM_REACHED' ? 'status-ready' : 'membership-status-pending'}`}>
                    {request.status === 'QUORUM_REACHED' ? 'READY TO APPLY' : request.panic_request_id ? 'PENDING' : 'SIGNATURE REQUIRED'}
                  </span>
                  <span>Proposed {formatDate(request.requested_at)}</span>
                </div>
                <h3>{fullName(request)}{isMe ? ' (you)' : ''}</h3>
                <p className="membership-email">
                  {request.email}{request.invited_by ? ` · proposed by ${request.invited_by}` : ''}
                </p>
                <dl className="panic-quorum-grid">
                  <div><dt>Accepted</dt><dd>{request.for_count} / {request.required_quorum}</dd></div>
                  <div><dt>Declined</dt><dd>{request.against_count} / {request.required_quorum}</dd></div>
                </dl>
                {canVote && dnsIntentEnabled ? (
                  request.panic_request_id ? (
                    <button className="commit-reveal-button" type="button" onClick={onReviewInvitations}>
                      Review signed invitation
                    </button>
                  ) : (
                    <>
                      <p className="field-note">This invitation needs a signed panic request. Previous unsigned votes do not count.</p>
                      <button className="commit-reveal-button" type="button" onClick={() => onInvite(request)}>
                        Prepare invitation JSON
                      </button>
                    </>
                  )
                ) : <p className="field-note">Waiting for the domain members to approve and apply this invitation.</p>}
              </article>
            );
          })}
        </div>
      )}

      {canVote && (
        <>
          <h3 className="members-subheading">Invite by email</h3>
          <label className="record-search">
            <span aria-hidden="true">⌕</span>
            <input type="search" autoComplete="off" value={candidateQuery}
              onChange={(event) => onCandidateQueryChange(event.target.value)}
              placeholder="Search by email" aria-label="Search registered users by email" />
          </label>
          {candidateQuery.trim().length < 2 ? (
            <p className="commit-empty">Enter at least 2 characters of an email to search.</p>
          ) : isSearchingCandidates ? (
            <p className="commit-empty">Searching…</p>
          ) : candidates.length === 0 ? (
            <p className="commit-empty">No available registered users match this email.</p>
          ) : (
            <div className="table-scroll">
              <table className="records-table members-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th className="actions-heading">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((candidate) => (
                    <tr key={candidate.user_id}>
                      <td className="record-name">{fullName(candidate)}</td>
                      <td>{candidate.email}</td>
                      <td className="record-actions">
                        <button
                          type="button"
                          disabled={invitingId !== null}
                          onClick={() => onInvite(candidate)}
                        >
                          {invitingId === candidate.user_id ? 'Inviting…' : 'Invite to domain'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <h3 className="members-subheading">All members</h3>
      <div className="table-scroll">
        <table className="records-table members-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Status</th>
              {dnsIntentEnabled && <th>Keys</th>}
            </tr>
          </thead>
          <tbody>
            {team.members.map((member) => {
              const pending = member.membership_status !== 'ACCEPTED';
              return (
                <tr key={member.user_id} className={pending ? 'is-pending-member' : ''}>
                  <td className="record-name">
                    {pending && <span className="pending-star" title="No privileges yet">★ </span>}
                    {fullName(member)}{member.user_id === userId ? ' (you)' : ''}
                  </td>
                  <td>{member.email}</td>
                  <td>
                    <span className={pending ? 'member-chip is-pending' : 'member-chip is-accepted'}>
                      {pending ? 'Pending · no privileges' : 'Accepted'}
                    </span>
                  </td>
                  {dnsIntentEnabled && <td>{member.has_intent_keys ? 'Registered' : '—'}</td>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
