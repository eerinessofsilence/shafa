import type { ChartPoint } from '../types';
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

interface LineChartProps {
  data: ChartPoint[];
  height?: number;
}

interface ChartTooltipEntry {
  color?: string;
  dataKey?: string | number;
  name?: string | number;
  payload?: ChartPoint;
  value?: string | number | null;
}

function getItemsDomain(data: ChartPoint[]) {
  const maxValue = Math.max(...data.map((item) => item.items), 1);
  return [0, Math.ceil(maxValue * 1.2)];
}

function getErrorsDomain(data: ChartPoint[]) {
  const maxValue = Math.max(...data.map((item) => item.errors), 1);
  return [0, Math.max(maxValue + 1, 3)];
}

function ChartTooltipContent({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ChartTooltipEntry[];
}) {
  if (!active || !payload?.length) {
    return null;
  }

  const deduplicatedEntries = payload.filter((entry, index, entries) => {
    const entryKey = String(entry.dataKey ?? entry.name ?? index);

    return (
      index ===
      entries.findIndex(
        (candidate, candidateIndex) =>
          String(candidate.dataKey ?? candidate.name ?? candidateIndex) ===
          entryKey,
      )
    );
  });

  const rawDate = deduplicatedEntries[0]?.payload?.date ?? '—';

  return (
    <div className="rounded-[14px] border border-[rgba(140,172,201,0.24)] bg-[linear-gradient(180deg,rgba(13,20,29,0.98),rgba(9,15,23,0.98))] px-4 py-3 shadow-[0_18px_40px_rgba(0,0,0,0.28)]">
      <div className="text-[15px] font-semibold text-[#f4f7fb]">
        {`Период: ${rawDate}`}
      </div>
      <div className="mt-2 space-y-1.5">
        {deduplicatedEntries.map((entry, index) => {
          const metricName =
            String(entry.dataKey ?? entry.name) === 'items' ? 'Товары' : 'Ошибки';

          return (
            <div
              key={String(entry.dataKey ?? entry.name ?? index)}
              className="flex items-center gap-2 text-[14px] text-[#c5d2e1]"
            >
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: entry.color ?? '#c5d2e1' }}
              />
              <span>{metricName}</span>
              <span className="ml-auto font-medium">{entry.value ?? 0}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function LineChart({ data, height = 280 }: LineChartProps) {
  return (
    <div
      className="overflow-hidden rounded-[12px] border border-border bg-[radial-gradient(circle_at_top,rgba(69,214,195,0.08),transparent_32%),linear-gradient(180deg,#24303d,#18212c)] px-3 py-4"
      style={{ height }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data}
          margin={{ top: 10, right: 10, bottom: 6, left: -16 }}
        >
          <defs>
            <linearGradient id="items-bar-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#45d6c3" stopOpacity={0.95} />
              <stop offset="100%" stopColor="#2a8f83" stopOpacity={0.45} />
            </linearGradient>
            <linearGradient id="items-area-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#45d6c3" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#45d6c3" stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid
            vertical={false}
            stroke="rgba(140,172,201,0.12)"
            strokeDasharray="4 8"
          />
          <XAxis
            dataKey="label"
            axisLine={false}
            interval="preserveStartEnd"
            minTickGap={18}
            tickLine={false}
            tick={{ fill: 'rgba(140,157,180,0.85)', fontSize: 13 }}
          />
          <YAxis
            yAxisId="items"
            axisLine={false}
            tickLine={false}
            tick={{ fill: 'rgba(140,157,180,0.7)', fontSize: 12 }}
            tickMargin={10}
            width={40}
            domain={getItemsDomain(data)}
          />
          <YAxis
            yAxisId="errors"
            orientation="right"
            allowDecimals={false}
            axisLine={false}
            tickLine={false}
            tick={{ fill: 'rgba(255,126,138,0.72)', fontSize: 12 }}
            tickMargin={10}
            width={32}
            domain={getErrorsDomain(data)}
          />
          <Tooltip
            cursor={{ fill: 'rgba(140,172,201,0.08)' }}
            content={<ChartTooltipContent />}
          />

          <Area
            yAxisId="items"
            type="monotone"
            dataKey="items"
            fill="url(#items-area-fill)"
            stroke="#6cf0df"
            strokeOpacity={0.8}
            strokeWidth={2}
            activeDot={false}
          />
          <Bar
            yAxisId="items"
            dataKey="items"
            fill="url(#items-bar-fill)"
            radius={[10, 10, 4, 4]}
            barSize={28}
          />
          <Line
            yAxisId="errors"
            type="monotone"
            dataKey="errors"
            stroke="#ff7e8a"
            strokeWidth={3}
            dot={{ r: 4, fill: '#ff7e8a', stroke: '#101821', strokeWidth: 2 }}
            activeDot={{
              r: 5,
              fill: '#ff7e8a',
              stroke: '#101821',
              strokeWidth: 2,
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
