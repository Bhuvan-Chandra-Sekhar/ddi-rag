import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

// Everything a test can plant in shared state is undone here, so no test
// depends on what ran before it:
//  - stubGlobal'd values (fetch, etc.) are restored to the real globals
//  - fake timers are switched off
//  - mocks go back to their original implementation. restoreAllMocks, not
//    resetAllMocks, on purpose: on this Vitest version reset replaces the
//    implementation with an empty function, which would wipe the
//    vi.fn(impl) defaults that vi.mock factories install (e.g. getUser).
afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true });
Object.defineProperty(window, 'requestAnimationFrame', { value: (callback) => setTimeout(callback, 0), writable: true });
Object.defineProperty(window, 'cancelAnimationFrame', { value: (id) => clearTimeout(id), writable: true });
