import { useState } from 'react';
import Header from './components/Header.jsx';
import Footer from './components/Footer.jsx';
import Home from './screens/Home.jsx';
import Checker from './screens/Checker.jsx';
import Scanning from './screens/Scanning.jsx';
import Results from './screens/Results.jsx';
import Auth from './screens/Auth.jsx';
import Dashboard from './screens/Dashboard.jsx';
import { getUser, setToken, setUser as persistUser, token } from './api.js';

const EMPTY_DRAFT = { checking: '', current: [], allergies: [], notes: '' };

// Top-level router — replaces the old shell()/renderX() DOM-swap pattern
// with real React state. `draft` is lifted here (it's the direct
// equivalent of the old module-level `_draft` object) since Results'
// "check another"/"start over" actions mutate the same state Checker reads.
export default function App() {
  const [view, setView] = useState(() => (token() ? 'dashboard' : 'home'));
  const [user, setUserState] = useState(getUser);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [resultsData, setResultsData] = useState(null);
  const [scanError, setScanError] = useState('');

  const nav = (next) => setView(next);

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

  return (
    <div className="min-h-screen flex flex-col">
      <Header view={view} user={user} onNav={nav} onSignOut={handleSignOut} />

      {view === 'home' && <Home user={user} onNav={nav} />}

      {view === 'checker' && (
        <>
          {scanError && (
            <div className="max-w-3xl mx-auto px-6 pt-6 -mb-4">
              <p className="text-[13px] font-medium" style={{ color: 'var(--critical)' }}>{scanError}</p>
            </div>
          )}
          <Checker draft={draft} setDraft={setDraft} onSubmit={handleSubmitCheck} />
        </>
      )}

      {view === 'scanning' && (
        <Scanning
          medications={[...(draft.checking ? [draft.checking] : []), ...draft.current]}
          allergies={draft.allergies}
          onDone={handleScanDone}
          onError={handleScanError}
        />
      )}

      {view === 'results' && resultsData && (
        <Results
          data={resultsData.data}
          checkingCount={resultsData.checkingCount}
          draft={draft}
          onNewCheck={() => {
            setDraft(EMPTY_DRAFT);
            setView('checker');
          }}
          onCheckAnother={() => {
            setDraft((d) => ({ ...d, checking: '' }));
            setView('checker');
          }}
        />
      )}

      {view === 'auth' && <Auth onAuthenticated={handleAuthenticated} onSkip={() => nav('checker')} />}

      {view === 'dashboard' && (
        token() ? (
          <Dashboard onSessionExpired={handleSignOut} />
        ) : (
          <Auth onAuthenticated={handleAuthenticated} onSkip={() => nav('checker')} />
        )
      )}

      <Footer />
    </div>
  );
}
