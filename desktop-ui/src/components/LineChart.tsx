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

function getItemsDomain(data: ChartPoint[]) {
  const maxValue = Math.max(...data.map((item) => item.items), 1);
  return [0, Math.ceil(maxValue * 1.2)];
}

function getErrorsDomain(data: ChartPoint[]) {
  const maxValue = Math.max(...data.map((item) => item.errors), 1);
  return [0, Math.max(maxValue + 1, 3)];
}

export function LineChart({ data, height = 280 }: LineChartProps) {
  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex justify-center gap-4 text-[#737685]">
        <span className="inline-flex items-center gap-2">
          <i className="h-2 w-2 rounded-full bg-[#45b99a]" />
          Items
        </span>
        <span className="inline-flex items-center gap-2">
          <i className="h-2 w-2 rounded-full bg-[#ef6b7c]" />
          Errors
        </span>
      </div>

      <div
        className="overflow-hidden rounded-[12px] border border-[#d7dce6] bg-[radial-gradient(circle_at_top,rgba(69,214,195,0.08),transparent_32%),linear-gradient(180deg,#24303d,#18212c)] px-3 py-4"
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
              contentStyle={{
                border: '1px solid rgba(140,172,201,0.24)',
                borderRadius: '14px',
                background:
                  'linear-gradient(180deg, rgba(13,20,29,0.98), rgba(9,15,23,0.98))',
                boxShadow: '0 18px 40px rgba(0, 0, 0, 0.28)',
              }}
              labelStyle={{ color: '#f4f7fb', fontWeight: 600 }}
              itemStyle={{ color: '#c5d2e1' }}
              formatter={(value, name) => [
                `${value ?? 0}`,
                String(name) === 'items' ? 'Товары' : 'Ошибки',
              ]}
              labelFormatter={(label) => `Период: ${label}`}
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
    </div>
  );
}
