import { Badge, Empty, Metric, Panel } from './ui';
import { money, utc } from '../utils/format';

export default function ModelEvaluation({ evaluation }) {
  if (!evaluation?.baseline || !evaluation?.ml) return <Panel title="Forecasting performance" subtitle="Baseline versus ML evaluation"><Empty title="Model evaluation not available" detail="Measured MAE, RMSE, sample count, evaluation period, and model version will appear when Member 1 supplies evaluation outputs. No ML improvement is claimed in mock mode." /></Panel>;
  const { baseline, ml } = evaluation;
  const improvement = baseline.mae_cents > 0 && Number.isSafeInteger(ml.mae_cents) ? (baseline.mae_cents - ml.mae_cents) / baseline.mae_cents * 100 : null;
  return <Panel title="Forecasting performance" subtitle={`Evaluation samples: ${evaluation.sample_count ?? '—'} · ${utc(evaluation.started_at, true)} to ${utc(evaluation.ended_at, true)} UTC`} action={improvement == null ? null : <Badge tone={improvement >= 0 ? 'good' : 'warning'}>{improvement >= 0 ? '' : '−'}{Math.abs(improvement).toFixed(1)}% MAE improvement</Badge>}>
    <div className="table-scroll"><table><thead><tr><th>Measured model</th><th>Version</th><th className="numeric">MAE</th><th className="numeric">RMSE</th></tr></thead><tbody>{[['Baseline', baseline], ['ML model', ml]].map(([label, model]) => <tr key={label}><td>{label}</td><td>{model.model_version ?? '—'}</td><td className="numeric">{money(model.mae_cents)}</td><td className="numeric">{money(model.rmse_cents)}</td></tr>)}</tbody></table></div>
  </Panel>;
}
