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
  dnsIntentEnabled,
  onVote,
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
        A new member gets privileges on this domain only after more than half of the {team.accepted_count} accepted
        members accept them ({team.required_quorum} votes).
      </p>

      <h3 className="members-subheading">Join requests</h3>
      {team.requests.length === 0 ? (
        <p className="commit-empty">No pending join requests.</p>
      ) : (
        <div className="commit-list">
          {team.requests.map((request) => {
            const isMe = request.user_id === userId;
            return (
              <article className="commit-item membership-request" key={request.membership_id}>
                <div className="commit-item-top">
                  <span className="commit-status membership-status-pending">★ PENDING</span>
                  <span>Requested {formatDate(request.requested_at)}</span>
                </div>
                <h3>{fullName(request)}{isMe ? ' (you)' : ''}</h3>
                <p className="membership-email">{request.email}</p>
                <dl className="panic-quorum-grid">
                  <div><dt>Accepted</dt><dd>{request.for_count} / {request.required_quorum}</dd></div>
                  <div><dt>Declined</dt><dd>{request.against_count} / {request.required_quorum}</dd></div>
                </dl>
                {request.user_vote ? (
                  <div className="panic-user-vote"><span>✓</span><p>Your vote: <strong>{request.user_vote}</strong></p></div>
                ) : isMe ? (
                  <p className="field-note">Waiting for the domain members to vote. You cannot vote on your own request.</p>
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
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
