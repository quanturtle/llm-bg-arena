// The Catan board as an SVG: terrain, number tokens, robber, harbours, roads and buildings.
import { seatColor, seatLabel } from "@/components/seat";
import type { CatanLayout, CatanObservation } from "@/games/catan/observation";

// Pixels per geometry unit (the hex radius) and the margin around the board, in hex radii.
const SCALE = 40;
const MARGIN = 1.5;

const TERRAIN_FILL: Record<string, string> = {
  forest: "#3f7a4a",
  pasture: "#9fcf7a",
  fields: "#e6c65a",
  hills: "#d0773f",
  mountains: "#8d8f94",
  desert: "#e8d8a8",
};
const PORT_STROKE: Record<string, string> = {
  wood: "#3f7a4a",
  sheep: "#6fae4a",
  wheat: "#c9a227",
  brick: "#d0773f",
  ore: "#6d6f74",
};

type Point = { x: number; y: number };

// Geometry y grows upward; SVG y grows downward.
function toSvg(point: Point): Point {
  return { x: point.x * SCALE, y: -point.y * SCALE };
}

function pointList(points: Point[]): string {
  return points.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ");
}

function viewBox(layout: CatanLayout): string {
  const xs = layout.vertices.map((vertex) => vertex.x);
  const ys = layout.vertices.map((vertex) => vertex.y);
  const left = (Math.min(...xs) - MARGIN) * SCALE;
  const top = (-Math.max(...ys) - MARGIN) * SCALE;
  const width = (Math.max(...xs) - Math.min(...xs) + 2 * MARGIN) * SCALE;
  const height = (Math.max(...ys) - Math.min(...ys) + 2 * MARGIN) * SCALE;
  return `${left} ${top} ${width} ${height}`;
}

function vertexPoint(layout: CatanLayout, vertexId: number): Point {
  return toSvg(layout.vertices[vertexId]);
}

function NumberToken({ centre, number }: { centre: Point; number: number }) {
  const hot = number === 6 || number === 8;
  return (
    <g>
      <circle cx={centre.x} cy={centre.y} r={0.32 * SCALE} fill="#f8f4e6" stroke={hot ? "#c0392b" : "#7a7568"} strokeWidth={1} />
      <text x={centre.x} y={centre.y} dominantBaseline="central" textAnchor="middle" fontSize={11} fontWeight={700} fill={hot ? "#c0392b" : "#1d1d1b"}>
        {number}
      </text>
    </g>
  );
}

// The robber stands beside the number token, clear of the six corners.
function Robber({ centre }: { centre: Point }) {
  const x = centre.x + 0.5 * SCALE;
  const y = centre.y;
  const body =
    `M ${x - 0.16 * SCALE} ${y + 0.18 * SCALE} ` +
    `Q ${x - 0.14 * SCALE} ${y - 0.1 * SCALE} ${x} ${y - 0.08 * SCALE} ` +
    `Q ${x + 0.14 * SCALE} ${y - 0.1 * SCALE} ${x + 0.16 * SCALE} ${y + 0.18 * SCALE} Z`;
  return (
    <g fill="#2b2b2b" stroke="#f6f5f1" strokeWidth={0.8}>
      <title>robber</title>
      <circle cx={x} cy={y - 0.18 * SCALE} r={0.11 * SCALE} />
      <path d={body} />
    </g>
  );
}

function Hexes({ layout, observation }: { layout: CatanLayout; observation: CatanObservation }) {
  return (
    <g>
      {layout.hexes.map((hex, hexId) => {
        const data = observation.hexes[hexId];
        const corners = layout.hex_vertices[hexId].map((vertexId) => vertexPoint(layout, vertexId));
        const centre = toSvg(hex);
        return (
          <g key={hexId}>
            <polygon points={pointList(corners)} fill={TERRAIN_FILL[data?.terrain ?? ""] ?? "#c9c7c0"} stroke="var(--background)" strokeWidth={2} />
            <text x={centre.x} y={centre.y - 0.62 * SCALE} dominantBaseline="central" textAnchor="middle" fontSize={9} fill="rgb(29 29 27 / 0.6)">
              h{hexId}
            </text>
            {data?.number != null ? <NumberToken centre={centre} number={data.number} /> : null}
            {observation.robber === hexId ? <Robber centre={centre} /> : null}
          </g>
        );
      })}
    </g>
  );
}

function portLabel(resource: string | null): string {
  return resource === null ? "3:1" : `2:1 ${resource}`;
}

// A harbour sits on a coastal edge; its marker is pushed outward from the board centre at the origin.
function Ports({ layout, observation }: { layout: CatanLayout; observation: CatanObservation }) {
  return (
    <g>
      {observation.ports.map((port) => {
        const edge = layout.edges[port.edge];
        if (!edge) return null;
        const [first, second] = edge.vertices.map((vertexId) => vertexPoint(layout, vertexId));
        const middle = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
        const distance = Math.hypot(middle.x, middle.y) || 1;
        const marker = { x: middle.x + (middle.x / distance) * 0.62 * SCALE, y: middle.y + (middle.y / distance) * 0.62 * SCALE };
        const width = 1.25 * SCALE;
        const height = 0.5 * SCALE;
        return (
          <g key={port.edge}>
            <title>{`e${port.edge} ${portLabel(port.resource)}`}</title>
            <line x1={middle.x} y1={middle.y} x2={marker.x} y2={marker.y} stroke="var(--muted-foreground)" strokeWidth={1} strokeDasharray="2 2" />
            <rect
              x={marker.x - width / 2}
              y={marker.y - height / 2}
              width={width}
              height={height}
              rx={height / 2}
              fill="var(--card)"
              stroke={port.resource ? (PORT_STROKE[port.resource] ?? "var(--border)") : "var(--border)"}
              strokeWidth={1.2}
            />
            <text x={marker.x} y={marker.y} dominantBaseline="central" textAnchor="middle" fontSize={8} fill="var(--foreground)">
              {portLabel(port.resource)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

// Roads stop short of both intersections so buildings stay visible.
function Roads({ layout, observation }: { layout: CatanLayout; observation: CatanObservation }) {
  return (
    <g>
      {observation.roads.map((owner, edgeId) => {
        const edge = layout.edges[edgeId];
        if (owner === null || !edge) return null;
        const [first, second] = edge.vertices.map((vertexId) => vertexPoint(layout, vertexId));
        const dx = second.x - first.x;
        const dy = second.y - first.y;
        const length = Math.hypot(dx, dy) || 1;
        const inset = 0.2 * SCALE;
        return (
          <line
            key={edgeId}
            x1={first.x + (dx / length) * inset}
            y1={first.y + (dy / length) * inset}
            x2={second.x - (dx / length) * inset}
            y2={second.y - (dy / length) * inset}
            stroke={seatColor(owner)}
            strokeWidth={6}
            strokeLinecap="round"
          >
            <title>{`e${edgeId} ${seatLabel(owner)} road`}</title>
          </line>
        );
      })}
    </g>
  );
}

function settlementShape(centre: Point): Point[] {
  const size = 0.17 * SCALE;
  return [
    { x: centre.x - size, y: centre.y + size },
    { x: centre.x - size, y: centre.y - size * 0.3 },
    { x: centre.x, y: centre.y - size * 1.2 },
    { x: centre.x + size, y: centre.y - size * 0.3 },
    { x: centre.x + size, y: centre.y + size },
  ];
}

function cityShape(centre: Point): Point[] {
  const size = 0.24 * SCALE;
  return [
    { x: centre.x - size, y: centre.y + size * 0.8 },
    { x: centre.x - size, y: centre.y - size * 0.3 },
    { x: centre.x - size * 0.5, y: centre.y - size },
    { x: centre.x, y: centre.y - size * 0.3 },
    { x: centre.x + size, y: centre.y - size * 0.3 },
    { x: centre.x + size, y: centre.y + size * 0.8 },
  ];
}

function Buildings({ layout, observation }: { layout: CatanLayout; observation: CatanObservation }) {
  return (
    <g>
      {observation.buildings.map((building, vertexId) => {
        if (!building || !layout.vertices[vertexId]) return null;
        const centre = vertexPoint(layout, vertexId);
        const isCity = building.kind === "city";
        return (
          <polygon
            key={vertexId}
            points={pointList(isCity ? cityShape(centre) : settlementShape(centre))}
            fill={seatColor(building.player)}
            stroke={isCity ? "#1d1d1b" : "#ffffff"}
            strokeWidth={isCity ? 1.6 : 1}
          >
            <title>{`v${vertexId} ${seatLabel(building.player)} ${building.kind}`}</title>
          </polygon>
        );
      })}
    </g>
  );
}

export function CatanBoardSvg({ layout, observation }: { layout: CatanLayout; observation: CatanObservation }) {
  return (
    <svg viewBox={viewBox(layout)} role="img" aria-label="Catan board" className="h-auto w-full select-none" fontFamily="var(--font-geist-sans)">
      <Hexes layout={layout} observation={observation} />
      <Ports layout={layout} observation={observation} />
      <g stroke="rgb(29 29 27 / 0.18)" strokeWidth={1}>
        {layout.edges.map((edge) => {
          const [first, second] = edge.vertices.map((vertexId) => vertexPoint(layout, vertexId));
          return <line key={edge.id} x1={first.x} y1={first.y} x2={second.x} y2={second.y} />;
        })}
      </g>
      <Roads layout={layout} observation={observation} />
      <g fill="rgb(29 29 27 / 0.35)">
        {layout.vertices.map((vertex) => {
          const point = toSvg(vertex);
          return <circle key={vertex.id} cx={point.x} cy={point.y} r={0.05 * SCALE} />;
        })}
      </g>
      <Buildings layout={layout} observation={observation} />
    </svg>
  );
}
