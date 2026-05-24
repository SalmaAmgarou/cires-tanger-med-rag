import './MessageBubble.css';

const ARABIC_RE = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/;

function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const isArabic = ARABIC_RE.test(message.content);
  const time = new Date(message.timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });
  const citations = message.citations || [];
  const hasCitations = !isUser && citations.length > 0;
  const confidence = message.confidence;

  return (
    <div className={`bubble-row ${isUser ? 'bubble-row--user' : 'bubble-row--ai'}`}>
      <div
        className={`bubble ${isUser ? 'bubble--user' : 'bubble--ai'} ${message.isError ? 'bubble--error' : ''}`}
        dir={isArabic ? 'rtl' : 'ltr'}
      >
        <p className="bubble-text" style={{ whiteSpace: 'pre-wrap' }}>{message.content}</p>

        {hasCitations && (
          <div className="bubble-citations">
            <div className="bubble-citations-label">Sources</div>
            {citations.map((c, i) => {
              const label = c.document_title || c.source_url || c.chunk_id;
              const page = c.page_number ? `, p.${c.page_number}` : '';
              return (
                <a
                  key={c.chunk_id || i}
                  className="bubble-citation"
                  href={c.source_url || '#'}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={c.excerpt || ''}
                >
                  <span className="bubble-citation-num">[{i + 1}]</span>
                  <span className="bubble-citation-doc">{label}{page}</span>
                </a>
              );
            })}
          </div>
        )}

        <span className="bubble-meta">
          {!isUser && confidence != null && (
            <span
              className="bubble-confidence"
              title={`Confidence ${(confidence * 100).toFixed(0)}%`}
              style={{
                color: confidence >= 0.7 ? '#1b873b' : confidence >= 0.4 ? '#b58900' : '#b1331a',
              }}
            >
              ● {(confidence * 100).toFixed(0)}%
            </span>
          )}
          <span className="bubble-time">{time}</span>
          {isUser && (
            <svg className="bubble-check" width="16" height="11" viewBox="0 0 16 11">
              <path d="M11.071.653a.457.457 0 0 0-.304-.102.493.493 0 0 0-.381.178l-6.19 7.636-2.405-2.272a.463.463 0 0 0-.336-.136.475.475 0 0 0-.349.158.437.437 0 0 0-.026.61l2.728 2.58a.472.472 0 0 0 .348.137.465.465 0 0 0 .37-.193l6.541-8.086a.432.432 0 0 0 .004-.51z" fill="currentColor" />
              <path d="M15.071.653a.457.457 0 0 0-.304-.102.493.493 0 0 0-.381.178l-6.19 7.636-1.2-1.136-.708.874 1.586 1.5a.472.472 0 0 0 .348.137.465.465 0 0 0 .37-.193l6.541-8.086a.432.432 0 0 0-.062-.808z" fill="currentColor" />
            </svg>
          )}
        </span>
      </div>
    </div>
  );
}

export default MessageBubble;
