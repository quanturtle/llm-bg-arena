import { defineGame, type BoardContext } from "@/games/define";
import { observationSchema, type PuertoRicoObservation } from "@/games/puerto-rico/observation";
import { PuertoRicoStatus, RolesStrip, TableStrip } from "@/games/puerto-rico/table";

function PuertoRicoBoard({ observation, context }: { observation: PuertoRicoObservation; context: BoardContext }) {
  return (
    <div className="@container flex flex-col gap-3">
      <PuertoRicoStatus observation={observation} match={context.match} />
      <RolesStrip observation={observation} />
      <TableStrip observation={observation} />
    </div>
  );
}

export const puertoRico = defineGame({
  schema: observationSchema,
  tabs: [{ id: "board", label: "Board", render: (observation, context) => <PuertoRicoBoard observation={observation} context={context} /> }],
  eventIcons: {},
});
