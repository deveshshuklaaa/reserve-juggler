import { backtest } from './mockEngine';
self.onmessage = ({ data }) => {
  try { self.postMessage({ result: backtest(data.input, data.policy) }); }
  catch (error) { self.postMessage({ error: error.message }); }
};
