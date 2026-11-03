"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts";

import { seatColor } from "@/components/seat";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
    <Card aria-label="Points" className="gap-2 py-4">
      <CardHeader className="px-4">
        <CardTitle className="text-sm">Points (max {max})</CardTitle>
      </CardHeader>
      <CardContent className="px-2">
        <ChartContainer config={config} className="aspect-auto h-40 w-full">
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
      </CardContent>
    </Card>
  );
}
