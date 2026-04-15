import type { ChartPoint } from '../types';

interface ProjectedPoint {
  x: number;
  y: number;
  value: number;
  label: string;
}

function buildPath(points: ProjectedPoint[]): string {
  return points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
    .join(' ');
}

function projectSeries(
  data: ChartPoint[],
  key: 'items' | 'errors',
  width: number,
  height: number,
  padding: number,
  maxValue: number,
): ProjectedPoint[] {
  const drawableWidth = width - padding * 2;
  const drawableHeight = height - padding * 2;

  return data.map((item, index) => {
    const x = padding + (drawableWidth / Math.max(data.length - 1, 1)) * index;
    const y =
      padding + drawableHeight - (item[key] / maxValue) * drawableHeight;
    return { x, y, value: item[key], label: item.label };
  });
}

interface LineChartProps {
  data: ChartPoint[];
  height?: number;
}

export function LineChart({ data, height = 280 }: LineChartProps) {
  const width = 900;
  const padding = 36;
  const maxValue = Math.max(
    ...data.flatMap((item) => [item.items, item.errors]),
    1,
  );
  const itemsPoints = projectSeries(
    data,
    'items',
    width,
    height,
    padding,
    maxValue,
  );
  const errorsPoints = projectSeries(
    data,
    'errors',
    width,
    height,
    padding,
    maxValue,
  );
  const gridLines = Array.from({ length: 4 }, (_, index) => {
    const y = padding + ((height - padding * 2) / 3) * index;
    return { y, key: index };
  });

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex justify-center gap-4 text-text-muted/75">
        <span className="inline-flex items-center gap-2">
          <i className="h-2 w-2 rounded-full bg-success/50" />
          Items
        </span>
        <span className="inline-flex items-center gap-2">
          <i className="h-2 w-2 rounded-full bg-error/50" />
          Errors
        </span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full overflow-hidden rounded-[20px] bg-[linear-gradient(180deg,rgba(15,23,33,0.95),rgba(9,15,23,0.98))]"
        role="img"
        aria-label="Статический график элементов и ошибок"
      >
        {gridLines.map((line) => (
          <line
            key={line.key}
            x1={padding}
            y1={line.y}
            x2={width - padding}
            y2={line.y}
            className="stroke-[rgba(140,172,201,0.11)]"
            strokeWidth={1}
          />
        ))}

        <path
          d={buildPath(itemsPoints)}
          className="fill-none stroke-[#45d6c3]"
          strokeWidth={4}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d={buildPath(errorsPoints)}
          className="fill-none stroke-[#ff7e8a]"
          strokeWidth={4}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {itemsPoints.map((point) => (
          <circle
            key={`items-${point.label}`}
            cx={point.x}
            cy={point.y}
            r="5"
            className="fill-[#45d6c3] stroke-[#45d6c3]"
          />
        ))}

        {errorsPoints.map((point) => (
          <circle
            key={`errors-${point.label}`}
            cx={point.x}
            cy={point.y}
            r="4"
            className="fill-[#ff7e8a] stroke-[#ff7e8a]"
          />
        ))}

        {itemsPoints.map((point) => (
          <text
            key={`label-${point.label}`}
            x={point.x}
            y={height - 8}
            textAnchor="middle"
            className="fill-[#8c9db4] text-[16px]"
          >
            {point.label}
          </text>
        ))}
      </svg>
    </div>
  );
}
