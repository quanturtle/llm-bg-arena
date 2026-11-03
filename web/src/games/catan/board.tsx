import { CatanBoardSvg } from "@/games/catan/board-svg";
import { layoutSchema, observationSchema, type CatanObservation } from "@/games/catan/observation";
import { defineGame, type BoardContext } from "@/games/define";

function CatanBoard({ observation, context }: { observation: CatanObservation; context: BoardContext }) {
  const layout = layoutSchema.safeParse(context.layout);
  if (!layout.success) return <p className="text-sm text-destructive">The Catan layout did not load: {layout.error.message}</p>;
  return (
    <div className="mx-auto w-full max-w-[760px]">
      <CatanBoardSvg layout={layout.data} observation={observation} />
    </div>
  );
}

export const catan = defineGame({
  schema: observationSchema,
  tabs: [{ id: "board", label: "Board", render: (observation, context) => <CatanBoard observation={observation} context={context} /> }],
  eventIcons: {},
});
