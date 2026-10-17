import { Area, AreaChart, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { money, utc } from '../utils/format';
import { Empty } from './ui';

const axis = { fontSize: 11, fill: '#86868b', fontFamily: '-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif' };
const tooltip = { background: '#fffffff5', border: '1px solid #e5e5e7', borderRadius: 14, fontSize: 12, boxShadow: '0 8px 30px #0000000d', padding: '12px 16px' };
const amountTick = (value) => money(Math.round(value), true).replace('.00', '');
const amountTooltip = (value, name) => [Array.isArray(value) ? value.map((item) => money(Math.round(item))).join(' – ') : money(Math.round(value)), name];
const commonMargin = { top: 12, right: 14, left: 4, bottom: 0 };

export function TimeChart({ data, series, height = 250, summary, forecast = false, currentTime }) {
  if (!data?.length) return <Empty title="No recorded history yet" detail="Advance the simulation to build the chart." />;
  return <figure className="chart-figure"><div style={{ height }} role="img" aria-label={summary}>
    <ResponsiveContainer width="100%" height="100%" minWidth={0}>
      <ComposedChart data={data} margin={commonMargin}>
        <CartesianGrid vertical={false} stroke="#efeff2" />
        <XAxis dataKey="timestamp" tickFormatter={(v) => utc(v)} tick={axis} axisLine={false} tickLine={false} minTickGap={42} dy={8} />
        <YAxis tickFormatter={amountTick} tick={axis} axisLine={false} tickLine={false} width={72} tickCount={5} />
        <Tooltip contentStyle={tooltip} labelFormatter={(v) => `${utc(v, true)} UTC`} formatter={amountTooltip} />
        {forecast && <Area type="linear" dataKey="band" name="Mock forecast interval" fill="#eaf2fb" stroke="none" connectNulls={false} isAnimationActive={false} />}
        {series.map((s) => <Line key={s.key} type="linear" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={s.width ?? 2.2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }} strokeDasharray={s.dashed ? '4 5' : undefined} connectNulls={false} isAnimationActive={false} />)}
        {currentTime && <ReferenceLine x={currentTime} stroke="#a4adbb" strokeDasharray="3 3" />}
      </ComposedChart>
    </ResponsiveContainer>
  </div><figcaption>{summary}</figcaption></figure>;
}

export function ComparisonBars({ data, fields, count = false, summary }) {
  if (!data?.length) return null;
  return <figure className="chart-figure"><div style={{ height: 240 }} role="img" aria-label={summary}>
    <ResponsiveContainer width="100%" height="100%" minWidth={0}><BarChart data={data} margin={{ top: 12, right: 16, left: 8, bottom: 0 }} barSize={32}>
      <CartesianGrid vertical={false} stroke="#edf0f5" />
      <XAxis dataKey="name" tick={{ ...axis, fontSize: 10 }} axisLine={false} tickLine={false} interval={0} />
      <YAxis tick={axis} width={64} tickFormatter={count ? undefined : amountTick} axisLine={false} tickLine={false} allowDecimals={!count} />
      <Tooltip contentStyle={tooltip} formatter={count ? undefined : amountTooltip} />
      {fields.map((field) => <Bar key={field.key} dataKey={field.key} name={field.name} fill={field.color} radius={[3, 3, 0, 0]} isAnimationActive={false} />)}
      {fields.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
      <ReferenceLine y={0} stroke="#d4dbe6" />
    </BarChart></ResponsiveContainer>
  </div><figcaption>{summary}</figcaption></figure>;
}
