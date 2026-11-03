"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts";

import { seatColor } from "@/components/seat";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import type { Outline } from "@/lib/api";

/** Each seat's public points per step, with the step on screen marked; a click seeks to that step. */
export function PointsChart({ outline, step, onSeek }: { outline: Outline; step: number; onSeek: (step: number) => void }) {
  const seats = outline.match.seats;
  const config: ChartConfig = Object.fromEntries(seats.map((seat) => [`p${seat.player}`, { label: `P${seat.player + 1}`, color: seatColor(seat.player) }]));
  const data = outline.scores.map((scores, index) => ({
    step: index,
    ...Object.fromEntries(scores.map((score) => [`p${score.player}`, score.points])),
  }));
  const max = Math.max(1, ...outline.scores.flatMap((scores) => scores.map((score) => score.points)));
  return (
    <section aria-label="Points" className="flex h-full flex-col gap-2">
      <h2 className="text-sm font-medium">Points (max {max})</h2>
      <ChartContainer config={config} className="aspect-auto h-72 w-full xl:h-auto xl:min-h-48 xl:flex-1">
        <LineChart
          data={data}
          margin={{ left: 0, right: 12, top: 4, bottom: 0 }}
          onClick={(state) => {
            if (state.activeLabel !== undefined) onSeek(Number(state.activeLabel));
          }}
        >
          <CartesianGrid vertical={false} />
          <XAxis dataKey="step" type="number" domain={[0, Math.max(1, data.length - 1)]} tickLine={false} axisLine={false} tickMargin={6} />
          <YAxis width={28} tickLine={false} axisLine={false} allowDecimals={false} />
          <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, payload) => `step ${payload[0]?.payload.step}`} />} />
          {seats.map((seat) => (
            <Line
              key={seat.player}
              dataKey={`p${seat.player}`}
              type="stepAfter"
              stroke={`var(--color-p${seat.player})`}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          ))}
          <ReferenceLine x={step} stroke="var(--muted-foreground)" strokeDasharray="3 3" />
        </LineChart>
      </ChartContainer>
    </section>
  );
}
