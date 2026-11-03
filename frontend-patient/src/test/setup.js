import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true });
Object.defineProperty(window, 'requestAnimationFrame', { value: (callback) => setTimeout(callback, 0), writable: true });
Object.defineProperty(window, 'cancelAnimationFrame', { value: (id) => clearTimeout(id), writable: true });
