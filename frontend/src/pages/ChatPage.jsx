import { useState, useRef, useEffect, useCallback } from 'react';
import ChatHeader from '../components/chat/ChatHeader';
import MessageBubble from '../components/chat/MessageBubble';
import TypingIndicator from '../components/chat/TypingIndicator';
import ChatInput from '../components/chat/ChatInput';
import { sendMessage } from '../api/client';
import './ChatPage.css';

function getDateLabel(date) {
  const today = new Date();
  const d = new Date(date);
  const diffDays = Math.floor((today - d) / 86400000);
  if (diffDays === 0 && today.getDate() === d.getDate()) return 'Today';
  if (diffDays <= 1 && today.getDate() - d.getDate() === 1) return 'Yesterday';
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

const SUGGESTED_QUERIES = [
  'What was Tanger Med container throughput in 2024?',
  "Quel est le chiffre d'affaires de Tanger Med en 2024 ?",
  'What services does CIRES Technologies offer?',
  'Quels engagements RSE pour Tanger Med en 2024 ?',
];

function ChatPage({ theme, toggleTheme }) {
  const [messages, setMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const submitQuestion = useCallback(async (text) => {
    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);
    setIsTyping(true);

    try {
      const data = await sendMessage(conversationId, text);
      if (!conversationId && data.conversation_id) {
        setConversationId(data.conversation_id);
      }
      const aiMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: data.reply,
        timestamp: new Date(),
        confidence: data.confidence,
        citations: data.citations || [],
        chunksFound: data.chunks_found,
        intent: data.intent,
      };
      setMessages(prev => [...prev, aiMsg]);
    } catch (err) {
      const errMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content:
          "Une erreur technique est survenue. Merci de réessayer dans un instant.\n" +
          'A technical error occurred. Please try again shortly.',
        timestamp: new Date(),
        isError: true,
      };
      setMessages(prev => [...prev, errMsg]);
    } finally {
      setIsTyping(false);
    }
  }, [conversationId]);

  const handleSend = useCallback((text) => {
    submitQuestion(text);
  }, [submitQuestion]);

  const renderMessages = () => {
    const elements = [];
    let lastDate = '';
    for (const msg of messages) {
      const label = getDateLabel(msg.timestamp);
      if (label !== lastDate) {
        lastDate = label;
        elements.push(
          <div key={`sep-${msg.id}`} className="chat-date-sep">
            <span>{label}</span>
          </div>
        );
      }
      elements.push(<MessageBubble key={msg.id} message={msg} />);
    }
    return elements;
  };

  return (
    <div className="chat-container">
      <ChatHeader theme={theme} toggleTheme={toggleTheme} />
      <div className="chat-messages">
        <div className="chat-messages-inner">
          {messages.length === 0 && (
            <div className="chat-empty">
              <div className="chat-empty-logo">
                <span className="chat-empty-logo-letter">TM</span>
              </div>
              <p className="chat-empty-text">Tanger Med · CIRES Technologies</p>
              <p className="chat-empty-sub">
                Documentation Assistant — French &amp; English
                <br />
                Ask anything about Tanger Med activity, financials, CSR commitments, or CIRES Technologies' services.
              </p>
              <div className="chat-empty-suggestions">
                {SUGGESTED_QUERIES.map(q => (
                  <button
                    key={q}
                    type="button"
                    className="chat-empty-suggestion"
                    onClick={() => submitQuestion(q)}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {renderMessages()}
          {isTyping && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>
      </div>
      <ChatInput onSend={handleSend} disabled={false} />
    </div>
  );
}

export default ChatPage;
