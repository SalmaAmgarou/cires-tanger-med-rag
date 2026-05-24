import { useState, useEffect, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import ChatPage from './pages/ChatPage';
import AdminPage from './pages/AdminPage';

function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('rag-theme') || 'light';
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('rag-theme', theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ChatPage theme={theme} toggleTheme={toggleTheme} />} />
        <Route path="/admin" element={<AdminPage theme={theme} toggleTheme={toggleTheme} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
