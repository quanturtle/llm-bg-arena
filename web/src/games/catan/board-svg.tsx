"use client";

// The Catan board as an SVG: textured terrain, number tokens, robber, harbours, roads and buildings.
// The terrain and parchment art live in web/public/catan; SOURCE.md there says where they come from.
import { useId } from "react";

import { seatColor, seatLabel } from "@/components/seat";
import type { CatanLayout, CatanObservation } from "@/games/catan/observation";

// Pixels per geometry unit (the hex radius) and the margin around the board, in hex radii.
const SCALE = 40;
const MARGIN = 1.5;
const ASSET_ROOT = "/catan";

const TERRAIN: Record<string, { label: string; art: string; fill: string }> = {
  forest: { label: "wood", art: `${ASSET_ROOT}/terrain/forest.webp`, fill: "#3f7a4a" },
  pasture: { label: "sheep", art: `${ASSET_ROOT}/terrain/pasture.webp`, fill: "#9fcf7a" },
  fields: { label: "wheat", art: `${ASSET_ROOT}/terrain/fields.webp`, fill: "#e6c65a" },
  hills: { label: "brick", art: `${ASSET_ROOT}/terrain/hills.webp`, fill: "#d0773f" },
  mountains: { label: "ore", art: `${ASSET_ROOT}/terrain/mountains.webp`, fill: "#8d8f94" },
  desert: { label: "desert", art: `${ASSET_ROOT}/terrain/desert.webp`, fill: "#e8d8a8" },
};

const PORT_ICON: Record<string, string> = {
  wood: `${ASSET_ROOT}/icons/wood.svg`,
  sheep: `${ASSET_ROOT}/icons/sheep.svg`,
  wheat: `${ASSET_ROOT}/icons/wheat.svg`,
  brick: `${ASSET_ROOT}/icons/brick.svg`,
  ore: `${ASSET_ROOT}/icons/ore.svg`,
};

const PIPS: Record<number, number> = { 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1 };

type Point = { x: number; y: number };

// Geometry y grows upward; SVG y grows downward.
function toSvg(point: Point): Point {
  return { x: point.x * SCALE, y: -point.y * SCALE };
}

function pointList(points: Point[]): string {
  return points.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ");
}

type Frame = { left: number; top: number; width: number; height: number };

function boardFrame(layout: CatanLayout): Frame {
  const xs = layout.vertices.map((vertex) => vertex.x);
  const ys = layout.vertices.map((vertex) => vertex.y);
  return {
    left: (Math.min(...xs) - MARGIN) * SCALE,
    top: (-Math.max(...ys) - MARGIN) * SCALE,
    width: (Math.max(...xs) - Math.min(...xs) + 2 * MARGIN) * SCALE,
    height: (Math.max(...ys) - Math.min(...ys) + 2 * MARGIN) * SCALE,
  };
}

function vertexPoint(layout: CatanLayout, vertexId: number): Point {
  return toSvg(layout.vertices[vertexId]);
}

function NumberToken({ uid, centre, number }: { uid: string; centre: Point; number: number }) {
  const hot = number === 6 || number === 8;
  const radius = 0.34 * SCALE;
  const pips = PIPS[number] ?? 0;
  const ink = hot ? "#a73325" : "#2a2118";
  return (
    <g filter={`url(#${uid}-token-shadow)`}>
      <circle cx={centre.x} cy={centre.y} r={radius} fill={`url(#${uid}-paper)`} stroke="#5b4127" strokeWidth={1.2} />
      <circle cx={centre.x} cy={centre.y} r={radius - 2.4} fill="none" stroke={hot ? "#b84a38" : "#c9b58e"} strokeWidth={0.8} />
      <text
        x={centre.x}
        y={centre.y - 2}
        dominantBaseline="central"
        textAnchor="middle"
        fontSize={14}
        fontWeight={800}
        fill={ink}
      >
        {number}
      </text>
      <g fill={hot ? "#b84a38" : "#6b5434"}>
        {Array.from({ length: pips }, (_, index) => (
          <circle key={index} cx={centre.x + (index - (pips - 1) / 2) * 3.1} cy={centre.y + 0.17 * SCALE} r={0.85} />
        ))}
      </g>
    </g>
  );
}

// The robber is a dark token beside the number token, clear of the six corners.
function Robber({ uid, centre }: { uid: string; centre: Point }) {
  const radius = 0.27 * SCALE;
  const icon = 0.34 * SCALE;
  const x = centre.x + 0.61 * SCALE;
  const y = centre.y + 0.12 * SCALE;
  return (
    <g filter={`url(#${uid}-token-shadow)`}>
      <title>robber</title>
      <circle cx={x} cy={y} r={radius} fill="#24211d" stroke="#f4ecd7" strokeWidth={1.2} />
      <image
        href={`${ASSET_ROOT}/icons/robber.svg`}
        x={x - icon / 2}
        y={y - icon / 2}
        width={icon}
        height={icon}
        preserveAspectRatio="xMidYMid meet"
      />
    </g>
  );
}

function HexTiles({ uid, layout, observation }: { uid: string; layout: CatanLayout; observation: CatanObservation }) {
  return (
    <g filter={`url(#${uid}-hex-shadow)`}>
      {layout.hexes.map((hex, hexId) => {
        const data = observation.hexes[hexId];
        const terrain = data ? TERRAIN[data.terrain] : undefined;
        const corners = layout.hex_vertices[hexId].map((vertexId) => vertexPoint(layout, vertexId));
        const centre = toSvg(hex);
        const art = terrain?.art;
        return (
          <g key={hexId}>
            <title>{`h${hexId} ${data?.terrain ?? "unknown"}${terrain && terrain.label !== data?.terrain ? ` (${terrain.label})` : ""}${data?.number != null ? ` ${data.number}` : ""}`}</title>
            <clipPath id={`${uid}-hex-${hexId}`}>
              <polygon points={pointList(corners)} />
            </clipPath>
            <polygon points={pointList(corners)} fill={terrain?.fill ?? "#c9c7c0"} />
            {art ? (
              <g clipPath={`url(#${uid}-hex-${hexId})`}>
                <image
                  href={art}
                  x={centre.x - 1.175 * SCALE}
                  y={centre.y - 1.175 * SCALE}
                  width={2.35 * SCALE}
                  height={2.35 * SCALE}
                  preserveAspectRatio="xMidYMid slice"
                />
                <polygon points={pointList(corners)} fill={`url(#${uid}-tile-shade)`} />
              </g>
            ) : null}
            <polygon points={pointList(corners)} fill="none" stroke="#3b2a17" strokeOpacity={0.82} strokeWidth={1.4} strokeLinejoin="round" />
            <polygon points={pointList(corners)} fill="none" stroke="#fff4d8" strokeOpacity={0.2} strokeWidth={0.6} strokeLinejoin="round" />
            <g pointerEvents="none">
              <rect
                x={centre.x - 0.17 * SCALE}
                y={centre.y - 0.69 * SCALE}
                width={0.34 * SCALE}
                height={0.15 * SCALE}
                rx={0.075 * SCALE}
                fill="rgb(20 16 10 / 0.42)"
              />
              <text
                x={centre.x}
                y={centre.y - 0.615 * SCALE}
                dominantBaseline="central"
                textAnchor="middle"
                fontSize={7}
                fontWeight={600}
                fill="#f7efdc"
              >
                h{hexId}
              </text>
            </g>
          </g>
        );
      })}
    </g>
  );
}

function NumberTokens({ uid, layout, observation }: { uid: string; layout: CatanLayout; observation: CatanObservation }) {
  return (
    <g>
      {layout.hexes.map((hex, hexId) => {
        const number = observation.hexes[hexId]?.number;
        if (number == null) return null;
        return <NumberToken key={hexId} uid={uid} centre={toSvg(hex)} number={number} />;
      })}
    </g>
  );
}

function Robbers({ uid, layout, observation }: { uid: string; layout: CatanLayout; observation: CatanObservation }) {
  if (observation.robber === null || !layout.hexes[observation.robber]) return null;
  return <Robber uid={uid} centre={toSvg(layout.hexes[observation.robber])} />;
}

function portLabel(resource: string | null): string {
  return resource === null ? "3:1" : `2:1 ${resource}`;
}

// A harbour sits on a coastal edge; its marker is pushed outward from the board centre at the origin.
function Ports({ uid, layout, observation }: { uid: string; layout: CatanLayout; observation: CatanObservation }) {
  return (
    <g>
      {observation.ports.map((port) => {
        const edge = layout.edges[port.edge];
        if (!edge) return null;
        const [first, second] = edge.vertices.map((vertexId) => vertexPoint(layout, vertexId));
        const middle = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
        const distance = Math.hypot(middle.x, middle.y) || 1;
        const marker = { x: middle.x + (middle.x / distance) * 0.7 * SCALE, y: middle.y + (middle.y / distance) * 0.7 * SCALE };
        const width = 1.55 * SCALE;
        const height = 0.56 * SCALE;
        const icon = 0.34 * SCALE;
        const resource = port.resource;
        return (
          <g key={port.edge} filter={`url(#${uid}-token-shadow)`}>
            <title>{`e${port.edge} ${portLabel(resource)}`}</title>
            <line
              x1={middle.x}
              y1={middle.y}
              x2={marker.x}
              y2={marker.y}
              stroke="rgb(247 239 220 / 0.62)"
              strokeWidth={1.2}
              strokeDasharray="2 2"
            />
            <rect
              x={marker.x - width / 2}
              y={marker.y - height / 2}
              width={width}
              height={height}
              rx={height / 2}
              fill={`url(#${uid}-paper)`}
              stroke="#5b4127"
              strokeWidth={1.2}
            />
            <image
              href={resource === null ? `${ASSET_ROOT}/icons/ship.svg` : (PORT_ICON[resource] ?? `${ASSET_ROOT}/icons/ship.svg`)}
              x={marker.x - width / 2 + 0.1 * SCALE}
              y={marker.y - icon / 2}
              width={icon}
              height={icon}
              preserveAspectRatio="xMidYMid meet"
            />
            <text
              x={marker.x + 0.2 * SCALE}
              y={marker.y}
              dominantBaseline="central"
              textAnchor="middle"
              fontSize={10}
              fontWeight={700}
              fill="#33261a"
            >
              {resource === null ? "3:1" : "2:1"}
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
        const inset = 0.19 * SCALE;
        const start = { x: first.x + (dx / length) * inset, y: first.y + (dy / length) * inset };
        const end = { x: second.x - (dx / length) * inset, y: second.y - (dy / length) * inset };
        return (
          <g key={edgeId}>
            <title>{`e${edgeId} ${seatLabel(owner)} road`}</title>
            <line x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke="#2a1d12" strokeOpacity={0.5} strokeWidth={8.4} strokeLinecap="round" />
            <line x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke={seatColor(owner)} strokeWidth={6} strokeLinecap="round" />
            <line x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke="rgb(255 255 255 / 0.32)" strokeWidth={1.5} strokeLinecap="round" />
          </g>
        );
      })}
    </g>
  );
}

function Settlement({ centre, color, label }: { centre: Point; color: string; label: string }) {
  const r = SCALE;
  const { x, y } = centre;
  return (
    <g>
      <title>{label}</title>
      <ellipse cx={x} cy={y + 0.17 * r} rx={0.2 * r} ry={0.07 * r} fill="rgb(0 0 0 / 0.28)" />
      <rect x={x - 0.13 * r} y={y - 0.03 * r} width={0.26 * r} height={0.2 * r} rx={0.015 * r} fill={color} stroke="#281b10" strokeWidth={1.1} />
      <polygon
        points={`${x - 0.19 * r},${y - 0.03 * r} ${x},${y - 0.24 * r} ${x + 0.19 * r},${y - 0.03 * r}`}
        fill={color}
        stroke="#281b10"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <polygon
        points={`${x},${y - 0.24 * r} ${x + 0.19 * r},${y - 0.03 * r} ${x + 0.19 * r},${y + 0.02 * r} ${x},${y - 0.18 * r}`}
        fill="rgb(0 0 0 / 0.18)"
      />
      <rect x={x - 0.035 * r} y={y + 0.05 * r} width={0.07 * r} height={0.12 * r} fill="rgb(40 27 16 / 0.58)" />
    </g>
  );
}

function City({ centre, color, label }: { centre: Point; color: string; label: string }) {
  const r = SCALE;
  const { x, y } = centre;
  return (
    <g>
      <title>{label}</title>
      <ellipse cx={x} cy={y + 0.2 * r} rx={0.28 * r} ry={0.08 * r} fill="rgb(0 0 0 / 0.28)" />
      <rect x={x - 0.25 * r} y={y - 0.1 * r} width={0.2 * r} height={0.3 * r} rx={0.02 * r} fill={color} stroke="#281b10" strokeWidth={1.1} />
      <rect x={x + 0.05 * r} y={y - 0.06 * r} width={0.2 * r} height={0.26 * r} rx={0.02 * r} fill={color} stroke="#281b10" strokeWidth={1.1} />
      <rect x={x - 0.07 * r} y={y + 0.01 * r} width={0.14 * r} height={0.19 * r} fill={color} stroke="#281b10" strokeWidth={1.1} />
      <polygon
        points={`${x - 0.28 * r},${y - 0.1 * r} ${x - 0.15 * r},${y - 0.3 * r} ${x - 0.02 * r},${y - 0.1 * r}`}
        fill={color}
        stroke="#281b10"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <polygon
        points={`${x + 0.02 * r},${y - 0.06 * r} ${x + 0.15 * r},${y - 0.26 * r} ${x + 0.28 * r},${y - 0.06 * r}`}
        fill={color}
        stroke="#281b10"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <polygon
        points={`${x - 0.15 * r},${y - 0.3 * r} ${x - 0.02 * r},${y - 0.1 * r} ${x - 0.02 * r},${y - 0.05 * r} ${x - 0.15 * r},${y - 0.25 * r}`}
        fill="rgb(0 0 0 / 0.18)"
      />
      <polygon
        points={`${x + 0.15 * r},${y - 0.26 * r} ${x + 0.28 * r},${y - 0.06 * r} ${x + 0.28 * r},${y - 0.01 * r} ${x + 0.15 * r},${y - 0.21 * r}`}
        fill="rgb(0 0 0 / 0.18)"
      />
      <rect x={x - 0.19 * r} y={y + 0.02 * r} width={0.05 * r} height={0.06 * r} fill="rgb(40 27 16 / 0.55)" />
      <rect x={x + 0.11 * r} y={y + 0.04 * r} width={0.05 * r} height={0.06 * r} fill="rgb(40 27 16 / 0.55)" />
      <rect x={x - 0.025 * r} y={y + 0.1 * r} width={0.05 * r} height={0.1 * r} fill="rgb(40 27 16 / 0.55)" />
    </g>
  );
}

function Buildings({ layout, observation }: { layout: CatanLayout; observation: CatanObservation }) {
  return (
    <g>
      {observation.buildings.map((building, vertexId) => {
        if (!building || !layout.vertices[vertexId]) return null;
        const centre = vertexPoint(layout, vertexId);
        const label = `v${vertexId} ${seatLabel(building.player)} ${building.kind}`;
        return building.kind === "city" ? (
          <City key={vertexId} centre={centre} color={seatColor(building.player)} label={label} />
        ) : (
          <Settlement key={vertexId} centre={centre} color={seatColor(building.player)} label={label} />
        );
      })}
    </g>
  );
}

function BoardDefs({ uid }: { uid: string }) {
  return (
    <defs>
      <linearGradient id={`${uid}-sea`} x1="0" y1="0" x2="0.65" y2="1">
        <stop offset="0" stopColor="#2d7f9c" />
        <stop offset="0.52" stopColor="#1f6a87" />
        <stop offset="1" stopColor="#124a62" />
      </linearGradient>
      <radialGradient id={`${uid}-vignette`} cx="50%" cy="46%" r="74%">
        <stop offset="0.58" stopColor="#062f45" stopOpacity="0" />
        <stop offset="1" stopColor="#062f45" stopOpacity="0.52" />
      </radialGradient>
      <linearGradient id={`${uid}-tile-shade`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0.55" stopColor="#1d140c" stopOpacity="0" />
        <stop offset="1" stopColor="#1d140c" stopOpacity="0.15" />
      </linearGradient>
      <pattern id={`${uid}-waves`} width="52" height="32" patternUnits="userSpaceOnUse">
        <path d="M0 24 q 13 -9 26 0 t 26 0" fill="none" stroke="#d7f2f7" strokeOpacity="0.15" strokeWidth="1.4" strokeLinecap="round" />
        <path d="M-26 12 q 13 -9 26 0 t 26 0" fill="none" stroke="#d7f2f7" strokeOpacity="0.11" strokeWidth="1.2" strokeLinecap="round" />
      </pattern>
      <pattern id={`${uid}-paper`} width="72" height="72" patternUnits="userSpaceOnUse">
        <image href={`${ASSET_ROOT}/parchment.webp`} width="72" height="72" preserveAspectRatio="xMidYMid slice" />
      </pattern>
      <filter id={`${uid}-token-shadow`} x="-40%" y="-40%" width="180%" height="180%">
        <feDropShadow dx="0" dy="1.4" stdDeviation="1.3" floodColor="#051c27" floodOpacity="0.5" />
      </filter>
      <filter id={`${uid}-hex-shadow`} x="-8%" y="-8%" width="116%" height="116%">
        <feDropShadow dx="0" dy="2.2" stdDeviation="2.4" floodColor="#062a3f" floodOpacity="0.58" />
      </filter>
    </defs>
  );
}

export function CatanBoardSvg({ layout, observation }: { layout: CatanLayout; observation: CatanObservation }) {
  const uid = useId().replace(/:/g, "");
  const frame = boardFrame(layout);
  return (
    // on desktop the SVG fills its box and keeps its proportions inside it
    <svg
      viewBox={`${frame.left} ${frame.top} ${frame.width} ${frame.height}`}
      role="img"
      aria-label="Catan board"
      className="block h-auto w-full select-none xl:absolute xl:inset-0 xl:h-full"
      fontFamily="var(--font-geist-sans)"
    >
      <title>Catan board</title>
      <BoardDefs uid={uid} />
      <rect
        x={frame.left + 0.5}
        y={frame.top + 0.5}
        width={frame.width - 1}
        height={frame.height - 1}
        rx={1.1 * SCALE}
        fill={`url(#${uid}-sea)`}
        stroke="#082e41"
        strokeWidth={1.2}
      />
      <rect x={frame.left + 0.5} y={frame.top + 0.5} width={frame.width - 1} height={frame.height - 1} rx={1.1 * SCALE} fill={`url(#${uid}-waves)`} />
      <rect x={frame.left + 0.5} y={frame.top + 0.5} width={frame.width - 1} height={frame.height - 1} rx={1.1 * SCALE} fill={`url(#${uid}-vignette)`} />
      <HexTiles uid={uid} layout={layout} observation={observation} />
      <NumberTokens uid={uid} layout={layout} observation={observation} />
      <Robbers uid={uid} layout={layout} observation={observation} />
      <Ports uid={uid} layout={layout} observation={observation} />
      <g stroke="rgb(20 16 10 / 0.24)" strokeWidth={1.3}>
        {layout.edges.map((edge) => {
          const [first, second] = edge.vertices.map((vertexId) => vertexPoint(layout, vertexId));
          return <line key={edge.id} x1={first.x} y1={first.y} x2={second.x} y2={second.y} />;
        })}
      </g>
      <g stroke="rgb(255 248 230 / 0.25)" strokeWidth={0.7}>
        {layout.edges.map((edge) => {
          const [first, second] = edge.vertices.map((vertexId) => vertexPoint(layout, vertexId));
          return <line key={edge.id} x1={first.x} y1={first.y} x2={second.x} y2={second.y} />;
        })}
      </g>
      <Roads layout={layout} observation={observation} />
      <g fill="rgb(20 16 10 / 0.3)">
        {layout.vertices.map((vertex) => {
          const point = toSvg(vertex);
          return <circle key={vertex.id} cx={point.x} cy={point.y} r={0.035 * SCALE} />;
        })}
      </g>
      <Buildings layout={layout} observation={observation} />
    </svg>
  );
}
