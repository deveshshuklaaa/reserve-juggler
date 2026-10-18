import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
afterEach(cleanup);
class ResizeObserverMock { observe() {} unobserve() {} disconnect() {} }
globalThis.ResizeObserver = ResizeObserverMock;
window.scrollTo = vi.fn();
window.matchMedia = vi.fn().mockImplementation((media) => ({ matches: false, media, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
