import { useNavigate } from 'react-router-dom';
import './ChatHeader.css';

function ChatHeader({ theme, toggleTheme }) {
  const navigate = useNavigate();

  return (
    <header className="chat-header">
      <div className="chat-header-avatar">TM</div>
      <div className="chat-header-info">
        <h1 className="chat-header-name">Tanger Med · CIRES Knowledge Assistant</h1>
        <p className="chat-header-status">
          <span className="chat-header-dot" />
          RAG online · FR / EN
        </p>
      </div>
      <button
        className="chat-header-icon-btn"
        onClick={toggleTheme}
        title={theme === 'light' ? 'Dark mode' : 'Light mode'}
      >
        {theme === 'light' ? (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
        ) : (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="5" />
            <line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
            <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
          </svg>
        )}
      </button>
      <button
        className="chat-header-icon-btn"
        onClick={() => navigate('/admin')}
        title="Admin Dashboard"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="7" height="7" rx="1" />
          <rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" />
          <rect x="14" y="14" width="7" height="7" rx="1" />
        </svg>
      </button>
    </header>
  );
}

export default ChatHeader;
