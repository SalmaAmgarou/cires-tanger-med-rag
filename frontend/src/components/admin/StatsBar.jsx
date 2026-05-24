import './StatsBar.css';

const ICONS = {
  conversations: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  ),
  confidence: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  ),
  escalations: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  ),
  documents: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="8" y1="13" x2="16" y2="13" />
      <line x1="8" y1="17" x2="16" y2="17" />
    </svg>
  ),
};

function StatCard({ label, value, color, icon, accent }) {
  return (
    <div className="stat-card">
      <div className="stat-card-accent" style={{ background: accent || 'var(--admin-primary)' }} />
      <div className="stat-card-body">
        <div className="stat-card-icon" style={color ? { color } : undefined}>
          {icon}
        </div>
        <div className="stat-card-content">
          <div className="stat-value" style={color ? { color } : undefined}>
            {value ?? '\u2014'}
          </div>
          <div className="stat-label">{label}</div>
        </div>
      </div>
    </div>
  );
}

function StatsBar({ stats, loading }) {
  if (loading && !stats) {
    return (
      <div className="stats-bar">
        <StatCard label="Conversations" value="..." icon={ICONS.conversations} />
        <StatCard label="Avg Confidence" value="..." icon={ICONS.confidence} />
        <StatCard label="Escalations" value="..." icon={ICONS.escalations} />
        <StatCard label="Corpus Chunks" value="..." icon={ICONS.documents} />
      </div>
    );
  }

  return (
    <div className="stats-bar">
      <StatCard
        label="Conversations"
        value={stats?.total_conversations ?? 0}
        icon={ICONS.conversations}
        accent="var(--admin-primary)"
      />
      <StatCard
        label="Avg Confidence"
        value={stats?.avg_confidence != null ? `${(stats.avg_confidence * 100).toFixed(0)}%` : '\u2014'}
        color={stats?.avg_confidence >= 0.7 ? 'var(--conf-high-text)' : 'var(--conf-medium-text)'}
        icon={ICONS.confidence}
        accent={stats?.avg_confidence >= 0.7 ? 'var(--conf-high-text)' : 'var(--conf-medium-text)'}
      />
      <StatCard
        label="Escalations"
        value={stats?.escalation_count ?? 0}
        color={stats?.escalation_count > 0 ? 'var(--admin-danger)' : undefined}
        icon={ICONS.escalations}
        accent={stats?.escalation_count > 0 ? 'var(--admin-danger)' : 'var(--admin-border)'}
      />
      <StatCard
        label={`Corpus Chunks (${stats?.total_documents ?? 0} docs)`}
        value={stats?.total_chunks ?? 0}
        icon={ICONS.documents}
        accent="var(--admin-primary)"
      />
    </div>
  );
}

export default StatsBar;
