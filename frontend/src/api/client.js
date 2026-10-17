import { createMockApi } from './mockTreasuryApi';
import { createRealApi } from './treasuryApi';

export const treasuryApi = import.meta.env.VITE_USE_MOCKS !== 'false'
  ? createMockApi() : createRealApi(import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || '');
