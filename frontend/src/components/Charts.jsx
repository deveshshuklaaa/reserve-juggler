import { Area, AreaChart, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { money, utc } from '../utils/format';
import { Empty } from './ui';

const axis = { fontSize: 13, fill: '#6e6e73', fontFamily: '-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif' };
const tooltip = {
  background: 'rgba(255, 255, 255, 0.95)',
  border: '1px solid #e5e5ea',
  borderRadius: 16,
  fontSize: 13,
  color: '#1d1d1f',
  boxShadow: '0 12px 32px rgba(0, 0, 0, 0.08)',
  padding: '12px 18px',
  backdropFilter: 'blur(16px)',
};
const amountTick = (value) => money(Math.round(value), true).replace('.00', '');
const amountTooltip = (value, name) => [Array.isArray(value) ? value.map((item) => money(Math.round(item))).join(' – ') : money(Math.round(value)), name];
const commonMargin = { top: 12, right: 14, left: 4, bottom: 0 };

export function TimeChart({ data, series, height = 260, summary, forecast = false, currentTime }) {
  if (!data?.length) return <Empty title="No recorded history yet" detail="Advance the simulation to build the chart." />;
  return <figure className="chart-figure"><div style={{ height }} role="img" aria-label={summary}>
    <ResponsiveContainer width="100%" height="100%" minWidth={0}>
      <ComposedChart data={data} margin={commonMargin}>
        <CartesianGrid vertical={false} stroke="#e5e5ea" />
        <XAxis dataKey="timestamp" tickFormatter={(v) => utc(v)} tick={axis} axisLine={false} tickLine={false} minTickGap={42} dy={8} />
        <YAxis tickFormatter={amountTick} tick={axis} axisLine={false} tickLine={false} width={76} tickCount={5} />
        <Tooltip contentStyle={tooltip} labelFormatter={(v) => `${utc(v, true)} UTC`} formatter={amountTooltip} />
        {forecast && <Area type="linear" dataKey="band" name="Mock forecast interval" fill="rgba(41, 151, 255, 0.15)" stroke="none" connectNulls={false} isAnimationActive={false} />}
        {series.map((s) => <Line key={s.key} type="linear" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={s.width ?? 2.8} dot={false} activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }} strokeDasharray={s.dashed ? '4 5' : undefined} connectNulls={false} isAnimationActive={false} />)}
        {currentTime && <ReferenceLine x={currentTime} stroke="#2997ff" strokeDasharray="3 3" />}
      </ComposedChart>
    </ResponsiveContainer>
  </div><figcaption>{summary}</figcaption></figure>;
}

export function ComparisonBars({ data, fields, count = false, summary }) {
  if (!data?.length) return null;
  return <figure className="chart-figure"><div style={{ height: 260 }} role="img" aria-label={summary}>
    <ResponsiveContainer width="100%" height="100%" minWidth={0}><BarChart data={data} margin={{ top: 12, right: 16, left: 8, bottom: 0 }} barSize={36}>
      <CartesianGrid vertical={false} stroke="#e5e5ea" />
      <XAxis dataKey="name" tick={{ ...axis, fontSize: 12 }} axisLine={false} tickLine={false} interval={0} />
      <YAxis tick={axis} width={68} tickFormatter={count ? undefined : amountTick} axisLine={false} tickLine={false} allowDecimals={!count} />
      <Tooltip contentStyle={tooltip} formatter={count ? undefined : amountTooltip} />
      {fields.map((field) => <Bar key={field.key} dataKey={field.key} name={field.name} fill={field.color} radius={[6, 6, 0, 0]} isAnimationActive={false} />)}
      {fields.length > 1 && <Legend wrapperStyle={{ fontSize: 13, color: '#a1a1a6' }} />}
      <ReferenceLine y={0} stroke="rgba(255, 255, 255, 0.15)" />
    </BarChart></ResponsiveContainer>
  </div><figcaption>{summary}</figcaption></figure>;
}
