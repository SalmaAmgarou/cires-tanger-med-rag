import './ConversationList.css';

function ConversationList({ conversations, selected, onSelect, loading }) {
  if (loading && conversations.length === 0) {
    return (
      <div className="conv-list">
        <div className="conv-list-empty">Loading conversations...</div>
      </div>
    );
  }

  if (conversations.length === 0) {
    return (
      <div className="conv-list">
        <div className="conv-list-empty">No conversations yet</div>
      </div>
    );
  }

  return (
    <div className="conv-list">
      {conversations.map(c => {
        const time = new Date(c.updated_at || c.created_at).toLocaleString([], {
          month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
        });
        const isEscalated = c.status === 'escalated';
        const confPct = (!isEscalated && c.confidence != null) ? (c.confidence * 100).toFixed(0) : null;
        const confLevel = c.confidence >= 0.7 ? 'high' : c.confidence >= 0.4 ? 'medium' : 'low';

        return (
          <button
            key={c.id}
            className={`conv-item ${selected === c.id ? 'conv-item--active' : ''}`}
            onClick={() => onSelect(c.id)}
          >
            <div className="conv-item-top">
              <span className="conv-item-id">
                {c.user_id || c.id.slice(0, 8)}
              </span>
              <span className="conv-item-time">{time}</span>
            </div>
            <div className="conv-item-bottom">
              <span className="conv-item-preview">{c.last_message || '...'}</span>
              <div className="conv-item-badges">
                {confPct != null && (
                  <span className={`conv-item-conf conv-item-conf--${confLevel}`}>{confPct}%</span>
                )}
                <span className={`conv-item-status conv-item-status--${c.status}`}>
                  {c.status}
                </span>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

export default ConversationList;
