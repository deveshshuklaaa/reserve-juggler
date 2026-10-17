import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { treasuryApi } from '../api/client';
import { DEFAULT_RUN } from '../mocks/constants';

const SimulationContext = createContext(null);
const emptyData = { snapshot: null, history: [], transactions: [], decisions: [], forecast: null };

export function SimulationProvider({ children, api = treasuryApi }) {
  const [data, setData] = useState(emptyData);
  const [busy, setBusy] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [comparison, setComparison] = useState(null);
  const [beforeShock, setBeforeShock] = useState(null);
  const [scheduled, setScheduled] = useState(null);
  const active = useRef(null);
  const controller = useRef(null);
  const version = useRef(0);
  const lock = useRef(false);
  const playRef = useRef(false);

  useEffect(() => () => { version.current += 1; controller.current?.abort(); playRef.current = false; }, []);

  const hydrate = useCallback(async (id, signal, token) => {
    const [snapshot, history, transactions, decisions, forecast] = await Promise.all([
      api.getSnapshot(id, { signal }), api.getHistory(id, { signal }),
      api.getTransactions(id, { signal }), api.getDecisions(id, { signal }), api.getForecast(id, 1440, { signal }),
    ]);
    if (token !== version.current || signal.aborted) return null;
    if (snapshot.run_id !== id) throw new Error('Response belongs to a different simulation.');
    active.current = snapshot;
    setData({ snapshot, history: history.items, transactions: transactions.items, decisions: decisions.items, forecast });
    if (snapshot.status === 'COMPLETED') { playRef.current = false; setPlaying(false); }
    return snapshot;
  }, [api]);

  const perform = useCallback(async (operation) => {
    if (lock.current || !active.current) return null;
    lock.current = true; setBusy(true); setError(''); setNotice('');
    const current = active.current; const token = version.current;
    const request = new AbortController(); controller.current = request;
    try {
      const result = await operation(current, request.signal);
      if (token !== version.current || request.signal.aborted) return null;
      await hydrate(current.run_id, request.signal, token);
      return result;
    } catch (err) {
      if (err.name !== 'AbortError' && token === version.current) {
        playRef.current = false; setPlaying(false);
        if (err.status === 409) {
          try { await hydrate(current.run_id, request.signal, token); setNotice('The run advanced elsewhere. The latest snapshot has been loaded.'); }
          catch { setError('Unable to refresh the conflicting run. Refresh before continuing.'); }
        } else setError(err.message || 'The operation failed. Refresh before continuing.');
      }
      return null;
    } finally {
      if (token === version.current) { lock.current = false; setBusy(false); }
    }
  }, [hydrate]);

  const createRun = useCallback(async (config = DEFAULT_RUN) => {
    if (lock.current) return;
    const token = ++version.current;
    controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    lock.current = true; setBusy(true); playRef.current = false; setPlaying(false);
    setError(''); setNotice(''); setData(emptyData); active.current = null;
    setComparison(null); setBeforeShock(null); setScheduled(null);
    try {
      await api.health({ signal: request.signal });
      const run = await api.createRun(config, { signal: request.signal });
      await hydrate(run.run_id, request.signal, token);
    } catch (err) { if (err.name !== 'AbortError' && token === version.current) setError(err.message); }
    finally { if (token === version.current) { lock.current = false; setBusy(false); } }
  }, [api, hydrate]);

  const advance = useCallback(() => perform((current, signal) => {
    if (current.status === 'COMPLETED') return current;
    return api.advanceRun(current.run_id, { expected_step: current.step }, { signal });
  }), [api, perform]);

  const refresh = useCallback(() => perform(async () => true), [perform]);
  const pause = useCallback(() => { playRef.current = false; setPlaying(false); }, []);
  const play = useCallback(() => {
    if (active.current && active.current.status !== 'COMPLETED' && !lock.current) {
      playRef.current = true; setPlaying(true); setError('');
    }
  }, []);

  useEffect(() => {
    if (!playing) return;
    let timer; let cancelled = false;
    const tick = async () => {
      if (cancelled || !playRef.current) return;
      if (!lock.current) await advance();
      if (!cancelled && playRef.current && active.current?.status !== 'COMPLETED') timer = setTimeout(tick, 1500);
    };
    timer = setTimeout(tick, 400);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [playing, advance]);

  const applyScenario = useCallback(async (body) => {
    pause(); const before = active.current ? structuredClone(active.current) : null;
    const result = await perform((current, signal) => api.applyScenario(current.run_id, body, { signal }));
    if (result) { setBeforeShock(before); setScheduled(result); setNotice(`Scenario scheduled for step ${result.effective_step}. Advance to observe the effect.`); }
    return result;
  }, [api, pause, perform]);
  const updatePolicy = useCallback(async (body) => {
    pause(); const result = await perform((current, signal) => api.updatePolicy(current.run_id, body, { signal }));
    if (result) setNotice('Policy applied. Existing vault terms are unchanged. New decisions use this policy.');
    return result;
  }, [api, pause, perform]);
  const runComparison = useCallback(async (body) => {
    pause(); setComparison(null);
    const result = await perform((current, signal) => api.runBacktest(current.run_id, body, { signal }));
    if (result) setComparison(result);
  }, [api, pause, perform]);
  const refreshComparison = useCallback(async () => {
    const result = await perform((current, signal) => api.getReport(current.run_id, { signal }));
    if (result) setComparison(result);
  }, [api, perform]);

  return <SimulationContext.Provider value={{ ...data, busy, playing, error, notice, comparison, beforeShock, scheduled,
    mode: api.mode, status: busy && !data.snapshot ? 'STARTING' : error ? 'ERROR' : !data.snapshot ? 'IDLE' : data.snapshot.status === 'COMPLETED' ? 'COMPLETED' : playing ? 'RUNNING' : 'PAUSED',
    createRun, advance, play, pause, refresh, applyScenario, updatePolicy, runComparison, refreshComparison,
  }}>{children}</SimulationContext.Provider>;
}

export function useSimulation() {
  const context = useContext(SimulationContext);
  if (!context) throw new Error('useSimulation requires SimulationProvider.');
  return context;
}
