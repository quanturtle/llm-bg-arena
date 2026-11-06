import { Flag, Handshake, PenLine, Trophy } from "lucide-react";
import { z } from "zod";

import { seatColor, seatLabel } from "@/components/seat";
import { defineGame, type BoardContext } from "@/games/define";
import { cn } from "@/lib/utils";

const observationSchema = z.object({
  board: z.array(z.string()),
  to_move: z.number().nullable(),
  winner: z.number().nullable(),
  line: z.array(z.string()),
  is_draw: z.boolean(),
});
type Observation = z.infer<typeof observationSchema>;

const MARK_SEAT: Record<string, number> = { X: 0, O: 1 };

function cellName(row: number, col: number): string {
  return String.fromCharCode(97 + col) + (row + 1);
}

function statusText(observation: Observation): string {
  if (observation.winner !== null) return `${seatLabel(observation.winner)} wins with ${observation.line.join(" ")}.`;
  if (observation.is_draw) return "Draw.";
  return observation.to_move === null ? "" : `${seatLabel(observation.to_move)} to move.`;
}

// `board` lists rows top first; row 1 is the bottom line.
function TicTacToeBoard({ observation, context }: { observation: Observation; context: BoardContext }) {
  const rows = observation.board.length;
  const cols = observation.board[0]?.length ?? 0;
  const winning = new Set(observation.line);
  const marked = context.frame.events.find((event) => event.kind === "marked");
  const last = marked && typeof marked.data.cell === "string" ? marked.data.cell : null;
  return (
    <div className="flex flex-col items-center gap-4 py-6">
      <div className="grid gap-1.5" style={{ gridTemplateColumns: `1.5rem repeat(${cols}, 4rem)` }}>
        {observation.board.map((line, index) => {
          const row = rows - 1 - index;
          return [
            <div key={`label-${row}`} className="flex items-center justify-center text-xs text-muted-foreground">
              {row + 1}
            </div>,
            ...Array.from(line).map((mark, col) => {
              const name = cellName(row, col);
              const seat = MARK_SEAT[mark];
              return (
                <div
                  key={name}
                  title={name}
                  style={seat === undefined ? undefined : { color: seatColor(seat) }}
                  className={cn(
                    "flex size-16 items-center justify-center rounded-lg border text-3xl font-bold",
                    winning.has(name) && "ring-2 ring-emerald-500",
                    name === last && "bg-muted",
                  )}
                >
                  {mark === "." ? "" : mark}
                </div>
              );
            }),
          ];
        })}
        <div />
        {Array.from({ length: cols }, (_, col) => (
          <div key={col} className="text-center text-xs text-muted-foreground">
            {String.fromCharCode(97 + col)}
          </div>
        ))}
      </div>
      <p className="h-5 text-sm text-muted-foreground">{statusText(observation)}</p>
    </div>
  );
}

export const ticTacToe = defineGame({
  schema: observationSchema,
  usesLayout: false,
  tabs: [{ id: "board", label: "Board", render: (observation, context) => <TicTacToeBoard observation={observation} context={context} /> }],
  eventIcons: { started: Flag, marked: PenLine, won: Trophy, drawn: Handshake },
});
