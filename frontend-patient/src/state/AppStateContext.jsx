import { createContext, useContext, useState } from 'react';
import { getUser, setToken, setUser as persistUser, token } from '../api.js';

const EMPTY_DRAFT = { checking: '', current: [], allergies: [], notes: '' };

// Owns the top-level view/session/in-progress-check state that used to
// live directly in App.jsx's body. Behavior is unchanged from that
// version — this only moves state ownership out of the router component
// and into its own module, reachable via useAppState() instead of props,
// so a component nested anywhere under AppStateProvider can read/update
// it without every intermediate component having to thread it through.
const AppStateContext = createContext(null);

export function AppStateProvider({ children }) {
  const [view, setView] = useState(() => (token() ? 'dashboard' : 'home'));
  const [user, setUserState] = useState(getUser);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [resultsData, setResultsData] = useState(null);
  const [scanError, setScanError] = useState('');

  const nav = (next) => {
    setView(next);
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  };

  const handleSubmitCheck = () => {
    setScanError('');
    setView('scanning');
  };

  const handleScanDone = (data) => {
    setResultsData({ data, checkingCount: draft.checking ? 1 : 0 });
    setView('results');
  };

  const handleScanError = (message) => {
    setScanError(message);
    setView('checker');
  };

  const handleSignOut = () => {
    setToken(null);
    persistUser(null);
    setUserState(null);
    setView('home');
  };

  const handleAuthenticated = (u) => {
    setUserState(u);
    setView('dashboard');
  };

  const handleStartOver = () => {
    setDraft(EMPTY_DRAFT);
    setView('checker');
  };

  const handleCheckAnother = () => {
    setDraft((d) => ({ ...d, checking: '' }));
    setView('checker');
  };

  const value = {
    view, user, draft, resultsData, scanError,
    nav, setDraft,
    handleSubmitCheck, handleScanDone, handleScanError,
    handleSignOut, handleAuthenticated, handleStartOver, handleCheckAnother,
  };

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState() {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error('useAppState() must be called within an AppStateProvider');
  return ctx;
}
