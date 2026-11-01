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
  busyId,
  candidates = [],
  invitingId,
  dnsIntentEnabled,
  onVote,
  onInvite,
  onRequestRemoval,
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
        Any accepted member can propose adding a registered user. The user gets privileges on this domain only
        after more than half of the {team.accepted_count} accepted members accept them ({team.required_quorum} votes).
      </p>

      <h3 className="members-subheading">Pending votes</h3>
      {team.requests.length === 0 ? (
        <p className="commit-empty">No users are waiting for a vote.</p>
      ) : (
        <div className="commit-list">
          {team.requests.map((request) => {
            const isMe = request.user_id === userId;
            return (
              <article className="commit-item membership-request" key={request.membership_id}>
                <div className="commit-item-top">
                  <span className="commit-status membership-status-pending">★ PENDING</span>
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
                {request.user_vote ? (
                  <div className="panic-user-vote"><span>✓</span><p>Your vote: <strong>{request.user_vote}</strong></p></div>
                ) : isMe ? (
                  <p className="field-note">Waiting for the domain members to vote. You cannot vote on your own membership.</p>
                ) : canVote ? (
                  <div className="reveal-actions panic-vote-actions">
                    <button
                      className="panic-reject-button"
                      type="button"
                      disabled={busyId === request.membership_id}
                      onClick={() => onVote(request, 'REJECT')}
                    >
                      <span>✕</span> DECLINE
                    </button>
                    <button
                      className="panic-accept-button"
                      type="button"
                      disabled={busyId === request.membership_id}
                      onClick={() => onVote(request, 'ACCEPT')}
                    >
                      <span>✓</span> ACCEPT
                    </button>
                  </div>
                ) : (
                  <p className="field-note">Only accepted members can vote.</p>
                )}
              </article>
            );
          })}
        </div>
      )}

      {canVote && (
        <>
          <h3 className="members-subheading">Registered users</h3>
          {candidates.length === 0 ? (
            <p className="commit-empty">Every registered user is already a member of this domain or waiting for a vote.</p>
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
                          {invitingId === candidate.user_id ? 'Adding…' : '+ Add to domain'}
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
              {dnsIntentEnabled && canVote && <th className="actions-heading">Action</th>}
            </tr>
          </thead>
          <tbody>
            {team.members.map((member) => {
              const pending = member.membership_status === 'PENDING';
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
                  {dnsIntentEnabled && canVote && (
                    <td className="record-actions">
                      {member.membership_status === 'ACCEPTED' && member.user_id !== userId ? (
                        <button
                          className="panic-reject-button"
                          type="button"
                          onClick={() => onRequestRemoval(member)}
                        >
                          Request removal
                        </button>
                      ) : '—'}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
