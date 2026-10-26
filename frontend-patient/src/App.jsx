import Header from './components/Header.jsx';
import Footer from './components/Footer.jsx';
import Home from './screens/Home.jsx';
import Checker from './screens/Checker.jsx';
import Scanning from './screens/Scanning.jsx';
import Results from './screens/Results.jsx';
import Auth from './screens/Auth.jsx';
import Dashboard from './screens/Dashboard.jsx';
import { token } from './api.js';
import { AppStateProvider, useAppState } from './state/AppStateContext.jsx';

// Top-level router. State ownership lives in AppStateContext — this
// component only reads it and renders the view it points to.
function AppShell() {
  const {
    view, user, draft, setDraft, resultsData, scanError,
    nav, handleSubmitCheck, handleScanDone, handleScanError,
    handleSignOut, handleAuthenticated, handleStartOver, handleCheckAnother,
  } = useAppState();

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
          onNewCheck={handleStartOver}
          onCheckAnother={handleCheckAnother}
        />
      )}

      {view === 'auth' && <Auth onAuthenticated={handleAuthenticated} onSkip={() => nav('checker')} />}
      {view === 'clinician' && <Auth mode="clinician" onAuthenticated={() => { window.location.href = '/clinical'; }} onSkip={() => nav('checker')} />}

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

export default function App() {
  return (
    <AppStateProvider>
      <AppShell />
    </AppStateProvider>
  );
}
