import { useMemo, useState } from 'react';
import './EscalationQueue.css';

const FILTER_TYPES = [
  { key: 'all',             label: 'All' },
  { key: 'low_confidence',  label: 'Low Confidence' },
  { key: 'human_request',   label: 'Human Request' },
  { key: 'other',           label: 'Other' },
];

const TYPE_COLORS = {
  low_confidence: '#6b7280',
  human_request:  '#8b5cf6',
  other:          '#94a3b8',
};

function classifyEscalation(e) {
  if (e.escalation_reason) return e.escalation_reason;
  if (e.intent === 'human_request') return 'human_request';
  if (e.confidence != null && e.confidence < 0.3) return 'low_confidence';
  return 'other';
}

function EscalationQueue({ escalations, loading, onStatusChange }) {
  const [activeFilter, setActiveFilter] = useState('all');

  const counts = useMemo(() => {
    const out = { low_confidence: 0, human_request: 0, other: 0 };
    escalations.forEach(e => {
      out[classifyEscalation(e)] = (out[classifyEscalation(e)] || 0) + 1;
    });
    return out;
  }, [escalations]);

  const filtered = activeFilter === 'all'
    ? escalations
    : escalations.filter(e => classifyEscalation(e) === activeFilter);

  if (loading && escalations.length === 0) {
    return <div className="esc-queue"><p className="esc-empty">Loading…</p></div>;
  }

  if (escalations.length === 0) {
    return (
      <div className="esc-queue">
        <p className="esc-empty">No escalations — the assistant is handling everything.</p>
      </div>
    );
  }

  return (
    <div className="esc-queue">
      <div className="esc-filters">
        {FILTER_TYPES.map(f => {
          const count = f.key === 'all' ? escalations.length : (counts[f.key] || 0);
          return (
            <button
              key={f.key}
              className={`esc-filter-pill${activeFilter === f.key ? ' esc-filter-pill--active' : ''}`}
              onClick={() => setActiveFilter(f.key)}
            >
              {f.label} ({count})
            </button>
          );
        })}
      </div>

      {filtered.length === 0 ? (
        <p className="esc-empty">No escalations match this filter.</p>
      ) : (
        filtered.map((e, i) => {
          const time = new Date(e.created_at).toLocaleString([], {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
          });
          const confPct = e.confidence != null ? (e.confidence * 100).toFixed(0) : null;
          const confLevel = e.confidence >= 0.7 ? 'high' : e.confidence >= 0.4 ? 'medium' : 'low';
          const escType = classifyEscalation(e);
          const escStatus = e.escalation_status || 'pending';

          return (
            <div key={i} className="esc-item">
              <div className="esc-item-top">
                <span className="esc-item-id">
                  {e.user_id || e.conversation_id?.slice(0, 8)}
                </span>
                <span className="esc-item-time">{time}</span>
              </div>

              <div
                className="esc-item-reason-badge"
                style={{ borderLeftColor: TYPE_COLORS[escType] || TYPE_COLORS.other }}
              >
                <span className="esc-item-reason-label">{escType.replace('_', ' ')}</span>
              </div>

              {e.last_user_message && (
                <p className="esc-item-msg">{e.last_user_message}</p>
              )}

              <div className="esc-item-details">
                {e.intent && <span className="esc-item-intent">{e.intent}</span>}
                {confPct != null && (
                  <span className={`esc-item-conf esc-item-conf--${confLevel}`}>
                    {confPct}%
                  </span>
                )}
              </div>

              {onStatusChange && (
                <div className="esc-item-actions">
                  <select
                    className="esc-status-select"
                    value={escStatus}
                    onChange={(ev) => onStatusChange(e.conversation_id, ev.target.value)}
                  >
                    <option value="pending">Pending</option>
                    <option value="in_review">In Review</option>
                    <option value="resolved">Resolved</option>
                    <option value="closed">Closed</option>
                  </select>
                </div>
              )}

              {e.reasoning && (
                <p className="esc-item-reason">{e.reasoning}</p>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}

export default EscalationQueue;
