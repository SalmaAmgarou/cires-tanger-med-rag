import { useState } from 'react';
import './ConversationDetail.css';

const ARABIC_RE = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/;

function ConfidenceBadge({ value }) {
  if (value == null) return null;
  const pct = (value * 100).toFixed(0);
  const level = value >= 0.7 ? 'high' : value >= 0.4 ? 'medium' : 'low';
  return <span className={`conf-badge conf-badge--${level}`}>{pct}%</span>;
}

function AuditPanel({ audit, citations }) {
  const [expanded, setExpanded] = useState(false);
  if (!audit) return null;

  const renderedCitations = (citations && citations.length > 0)
    ? citations
    : (audit.citations || []);

  return (
    <div className="audit-panel">
      <button className="audit-toggle" onClick={() => setExpanded(!expanded)}>
        <span className="audit-toggle-icon">{expanded ? '▼' : '▶'}</span>
        <span className="audit-toggle-label">AI Decision</span>
        <ConfidenceBadge value={audit.confidence} />
        {audit.intent && <span className="audit-intent-badge">{audit.intent}</span>}
        {audit.language && <span className="audit-intent-badge">{audit.language.toUpperCase()}</span>}
        {audit.duration_ms != null && <span className="audit-duration">{audit.duration_ms}ms</span>}
      </button>

      {expanded && (
        <div className="audit-detail">
          {audit.search_query && (
            <div className="audit-section">
              <div className="audit-section-title">Search Query</div>
              <code className="audit-query">{audit.search_query}</code>
            </div>
          )}

          {renderedCitations.length > 0 && (
            <div className="audit-section">
              <div className="audit-section-title">Citations ({renderedCitations.length})</div>
              <div className="audit-results">
                {renderedCitations.map((c, j) => (
                  <div key={j} className="audit-result-item">
                    <span className="audit-result-score">[{j + 1}]</span>
                    <a
                      className="audit-result-title"
                      href={c.source_url || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {c.document_title || c.chunk_id}
                      {c.page_number ? `, p.${c.page_number}` : ''}
                    </a>
                  </div>
                ))}
              </div>
            </div>
          )}

          {audit.search_results && audit.search_results.length > 0 && (
            <div className="audit-section">
              <div className="audit-section-title">Top Retrieved Chunks ({audit.search_results.length})</div>
              <div className="audit-results">
                {audit.search_results.slice(0, 6).map((r, j) => (
                  <div key={j} className="audit-result-item">
                    <span className="audit-result-score">{(r.score * 100).toFixed(0)}%</span>
                    <span className="audit-result-title">
                      {r.document_title}
                      {r.page_number ? `, p.${r.page_number}` : ''}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {audit.reasoning && (
            <div className="audit-section">
              <div className="audit-section-title">Reasoning</div>
              <p className="audit-reasoning">{audit.reasoning}</p>
            </div>
          )}

          {audit.pipeline_steps && audit.pipeline_steps.length > 0 && (
            <div className="audit-section">
              <div className="audit-section-title">Pipeline</div>
              <div className="audit-pipeline">
                {audit.pipeline_steps.map((step, j) => (
                  <span key={j} className="audit-step">
                    {step.step}
                    {step.model && <span className="audit-step-model">{step.model}</span>}
                    {step.duration_ms != null && <span className="audit-step-ms">{step.duration_ms}ms</span>}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ConversationDetail({ detail }) {
  if (!detail) {
    return (
      <div className="conv-detail conv-detail--empty">
        <p>Select a conversation to view details</p>
      </div>
    );
  }

  return (
    <div className="conv-detail">
      <div className="conv-detail-header">
        <h3>{detail.user_id || detail.id?.slice(0, 8)}</h3>
        <span className={`conv-detail-status conv-detail-status--${detail.status}`}>
          {detail.status}
        </span>
      </div>

      <div className="conv-detail-messages">
        {(detail.messages || []).map((msg, i) => {
          const isUser = msg.role === 'user';
          const isArabic = ARABIC_RE.test(msg.content);
          const time = new Date(msg.created_at).toLocaleTimeString([], {
            hour: '2-digit', minute: '2-digit',
          });

          return (
            <div key={i} className={`detail-msg ${isUser ? 'detail-msg--user' : 'detail-msg--ai'}`}>
              <div className="detail-msg-header">
                <span className="detail-msg-role">{isUser ? 'User' : 'Assistant'}</span>
                <span className="detail-msg-time">{time}</span>
              </div>
              <p
                className="detail-msg-text"
                dir={isArabic ? 'rtl' : 'ltr'}
                style={{ whiteSpace: 'pre-wrap' }}
              >
                {msg.content}
              </p>
              {!isUser && (
                <AuditPanel audit={msg.audit} citations={msg.citations} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default ConversationDetail;
