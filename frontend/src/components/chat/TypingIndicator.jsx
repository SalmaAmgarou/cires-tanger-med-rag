import './TypingIndicator.css';

function TypingIndicator() {
  return (
    <div className="bubble-row bubble-row--ai">
      <div className="bubble bubble--ai typing-bubble">
        <div className="typing-dots">
          <span className="typing-dot" />
          <span className="typing-dot" />
          <span className="typing-dot" />
        </div>
      </div>
    </div>
  );
}

export default TypingIndicator;
