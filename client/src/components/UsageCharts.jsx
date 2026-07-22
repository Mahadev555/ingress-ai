import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  LineChart,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { BarChart3 } from "lucide-react";
import { Card, CardHeader, EmptyState } from "./ui.jsx";
import {
  SERIES_COLORS,
  statusColor,
  dayRange,
  shortDay,
  pivotRequests,
  pivotErrors,
  pivotByModel,
} from "../lib/timeseries.js";

const fmt = (n) => new Intl.NumberFormat().format(n ?? 0);

const AXIS = { fontSize: 11, fill: "#94a3b8" };
const GRID = "#f1f5f9";
const TOOLTIP_STYLE = {
  borderRadius: 10,
  border: "1px solid #e2e8f0",
  fontSize: 12,
  boxShadow: "0 4px 12px rgb(15 23 42 / 0.08)",
};

function ChartCard({ title, subtitle, children }) {
  return (
    <Card>
      <CardHeader title={title} subtitle={subtitle} />
      <div className="p-4">
        <ResponsiveContainer width="100%" height={220}>
          {children}
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

const commonAxes = (
  <>
    <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
    <XAxis dataKey="day" tickFormatter={shortDay} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={24} />
  </>
);

// One <Line> per model, colored from the shared palette.
function ModelLines({ keys }) {
  return keys.map((k, i) => (
    <Line
      key={k}
      type="monotone"
      dataKey={k}
      stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
      strokeWidth={2}
      dot={false}
      activeDot={{ r: 3 }}
    />
  ));
}

export default function UsageCharts({ rows, days = 14 }) {
  if (!rows || rows.length === 0) {
    return (
      <Card>
        <CardHeader title="Usage over time" subtitle={`Daily activity, last ${days} days`} />
        <EmptyState
          icon={BarChart3}
          title="No data to chart yet"
          description="Send a few requests from the playground, then refresh to see trends here."
        />
      </Card>
    );
  }

  const dayList = dayRange(days);
  const requests = pivotRequests(rows, dayList);
  const errors = pivotErrors(rows, dayList);
  const inputTokens = pivotByModel(rows, dayList, "prompt_tokens");
  const outputTokens = pivotByModel(rows, dayList, "completion_tokens");
  const modelRequests = pivotByModel(rows, dayList, "requests");

  const legend = { fontSize: 11, iconType: "circle", iconSize: 8 };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Total requests + success rate */}
        <div className="lg:col-span-2">
          <ChartCard title="Total API requests" subtitle="Requests per day and success rate">
            <ComposedChart data={requests} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
              {commonAxes}
              <YAxis yAxisId="left" tick={AXIS} tickLine={false} axisLine={false} width={40} />
              <YAxis
                yAxisId="right"
                orientation="right"
                domain={[0, 100]}
                unit="%"
                tick={AXIS}
                tickLine={false}
                axisLine={false}
                width={40}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={shortDay} />
              <Legend wrapperStyle={legend} />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="requests"
                name="Requests"
                stroke="#6366f1"
                fill="#6366f1"
                fillOpacity={0.12}
                strokeWidth={2}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="successRate"
                name="Success rate"
                stroke="#10a37f"
                strokeWidth={2}
                dot={false}
                connectNulls
              />
            </ComposedChart>
          </ChartCard>
        </div>

        {/* Errors by status */}
        <ChartCard title="Total API errors" subtitle="4xx / 5xx responses by status">
          {errors.keys.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-slate-400">
              No errors in this window 🎉
            </div>
          ) : (
            <BarChart data={errors.data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
              {commonAxes}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={32} allowDecimals={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={shortDay} />
              <Legend wrapperStyle={legend} />
              {errors.keys.map((k) => (
                <Bar key={k} dataKey={k} name={k} stackId="err" fill={statusColor(k)} radius={[2, 2, 0, 0]} />
              ))}
            </BarChart>
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <ChartCard title="Input tokens per model" subtitle="Prompt tokens per day">
          <LineChart data={inputTokens.data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
            {commonAxes}
            <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} tickFormatter={fmt} />
            <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={shortDay} />
            <Legend wrapperStyle={legend} />
            <ModelLines keys={inputTokens.keys} />
          </LineChart>
        </ChartCard>

        <ChartCard title="Output tokens per model" subtitle="Completion tokens per day">
          <LineChart data={outputTokens.data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
            {commonAxes}
            <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} tickFormatter={fmt} />
            <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={shortDay} />
            <Legend wrapperStyle={legend} />
            <ModelLines keys={outputTokens.keys} />
          </LineChart>
        </ChartCard>

        <ChartCard title="Requests per model" subtitle="Request count per day">
          <LineChart data={modelRequests.data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
            {commonAxes}
            <YAxis tick={AXIS} tickLine={false} axisLine={false} width={32} allowDecimals={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={shortDay} />
            <Legend wrapperStyle={legend} />
            <ModelLines keys={modelRequests.keys} />
          </LineChart>
        </ChartCard>
      </div>
    </div>
  );
}
