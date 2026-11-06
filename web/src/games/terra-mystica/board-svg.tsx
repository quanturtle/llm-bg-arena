"use client";

// The Terra Mystica map as an SVG: terrain hexes, transformed tiles and every player's buildings.
// Coordinates are the game's axial ones, so an action like "build 3,5" points at the labelled hex.
import { useId } from "react";

import { seatLabel } from "@/components/seat";
import {
  BUILDING_LABEL,
  TERRAINS,
  TERRAIN_META,
  factionMeta,
  type BuildingType,
  type Terrain,
  type TerrainSymbol as TerrainSymbolName,
} from "@/games/terra-mystica/meta";
import type { TerraMysticaPlayer, TerraMysticaTile } from "@/games/terra-mystica/observation";
import type { EventRecord } from "@/lib/api";

// Pixels per hex radius and the margin around the outermost corners, in hex radii.
const SCALE = 34;
const MARGIN = 0.35;
const SQRT3 = Math.sqrt(3);
const CORNER_ANGLES = Array.from({ length: 6 }, (_, step) => (Math.PI / 180) * (30 + 60 * step));

type Point = { x: number; y: number };

// Pointy-top axial layout with row 0 on top, as on the printed map: x = sqrt(3) * (q + r / 2), y = 1.5 * r.
function centre(q: number, r: number): Point {
  return { x: SQRT3 * (q + r / 2), y: 1.5 * r };
}

function toSvg(point: Point): Point {
  return { x: point.x * SCALE, y: point.y * SCALE };
}

function cornersAround(point: Point): Point[] {
  return CORNER_ANGLES.map((angle) => toSvg({ x: point.x + Math.cos(angle), y: point.y + Math.sin(angle) }));
}

function pointList(points: Point[]): string {
  return points.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ");
}

function tileKey(q: number, r: number): string {
  return `${q},${r}`;
}

type Frame = { left: number; top: number; width: number; height: number };

function boardFrame(tiles: TerraMysticaTile[]): Frame {
  const centres = tiles.map((tile) => centre(tile.q, tile.r));
  const xs = centres.map((point) => point.x);
  const ys = centres.map((point) => point.y);
  const minX = Math.min(...xs) - 1 - MARGIN;
  const maxX = Math.max(...xs) + 1 + MARGIN;
  const minY = Math.min(...ys) - 1 - MARGIN;
  const maxY = Math.max(...ys) + 1 + MARGIN;
  return {
    left: minX * SCALE,
    top: minY * SCALE,
    width: (maxX - minX) * SCALE,
    height: (maxY - minY) * SCALE,
  };
}

// The last action's tile gets a coloured outline: gold for a new building, green for new terrain.
const TOUCHED_COLOURS: Record<string, string> = {
  dwelling_placed: "#f3c969",
  built: "#f3c969",
  upgraded: "#f3c969",
  town_founded: "#c99cf0",
  transformed: "#7fd18c",
  cult_spade_used: "#7fd18c",
};

function touchedTiles(events: EventRecord[]): Map<string, string> {
  const touched = new Map<string, string>();
  for (const event of events) {
    const position = event.data.position;
    const colour = TOUCHED_COLOURS[event.kind];
    if (typeof position === "string" && colour) touched.set(position, colour);
  }
  return touched;
}

const BUILDING_PATHS: Record<BuildingType, { d: string; rule?: "evenodd" }> = {
  dwelling: { d: "M -0.34 0.28 L -0.34 -0.02 L 0 -0.34 L 0.34 -0.02 L 0.34 0.28 Z" },
  trading_house: {
    d: "M -0.44 0.30 L -0.44 -0.04 L -0.20 -0.24 L 0 -0.04 L 0.20 -0.24 L 0.44 -0.04 L 0.44 0.30 Z",
  },
  temple: {
    d: "M -0.42 0.30 L -0.42 -0.02 L 0 -0.40 L 0.42 -0.02 L 0.42 0.30 Z M -0.25 0.12 L -0.15 0.12 L -0.15 0.30 L -0.25 0.30 Z M -0.05 0.12 L 0.05 0.12 L 0.05 0.30 L -0.05 0.30 Z M 0.15 0.12 L 0.25 0.12 L 0.25 0.30 L 0.15 0.30 Z",
    rule: "evenodd",
  },
  stronghold: {
    d: "M -0.40 0.30 L -0.40 -0.18 L -0.24 -0.18 L -0.24 -0.34 L -0.08 -0.34 L -0.08 -0.18 L 0.08 -0.18 L 0.08 -0.34 L 0.24 -0.34 L 0.24 -0.18 L 0.40 -0.18 L 0.40 0.30 Z M -0.08 0.30 L -0.08 0.10 L 0.08 0.10 L 0.08 0.30 Z",
    rule: "evenodd",
  },
  sanctuary: {
    d: "M 0 -0.42 L 0.12 -0.13 L 0.42 0 L 0.12 0.13 L 0 0.42 L -0.12 0.13 L -0.42 0 L -0.12 -0.13 Z",
  },
};

function BuildingToken({ tile, centre: at, faction }: { tile: TerraMysticaTile; centre: Point; faction: string }) {
  const building = tile.building;
  if (!building) return null;
  const point = toSvg(at);
  const size = SCALE * 0.84;
  const path = BUILDING_PATHS[building.type];
  const style = factionMeta(faction);
  const label = `${seatLabel(building.owner)} ${BUILDING_LABEL[building.type].toLowerCase()} at ${tileKey(tile.q, tile.r)}${building.in_town ? " in a town" : ""}`;
  return (
    <g transform={`translate(${point.x} ${point.y})`}>
      <title>{label}</title>
      {building.in_town ? (
        <circle cx={0} cy={0} r={SCALE * 0.46} fill="none" stroke="#e9c15c" strokeWidth={1.4} strokeDasharray="2.4 2.4" />
      ) : null}
      <ellipse cx={0} cy={SCALE * 0.2} rx={SCALE * 0.36} ry={SCALE * 0.1} fill="rgb(0 0 0 / 0.26)" />
      <g transform={`scale(${size})`}>
        <path
          d={path.d}
          fillRule={path.rule}
          fill={style.color}
          stroke={style.border}
          strokeWidth={0.065}
          strokeLinejoin="round"
        />
        <path
          d={path.d}
          fillRule={path.rule}
          fill="none"
          stroke="rgb(255 255 255 / 0.34)"
          strokeWidth={0.03}
          strokeLinejoin="round"
          transform="scale(0.86)"
        />
      </g>
    </g>
  );
}

export function TerrainSymbol({
  symbol,
  color,
  size = 10,
  strokeWidth = 1.3,
}: {
  symbol: TerrainSymbolName;
  color: string;
  size?: number;
  strokeWidth?: number;
}) {
  const half = size / 2;
  const line = {
    stroke: color,
    strokeWidth,
    fill: "none",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  switch (symbol) {
    case "wasteland":
      return <circle r={half * 0.62} fill={color} />;
    case "swamp":
      return <circle r={half * 0.34} fill={color} />;
    case "desert":
      return <path d={`M ${-half * 0.85} 0 H ${half * 0.85}`} {...line} />;
    case "plains":
      return <path d={`M ${-half * 0.85} ${half * 0.3} Q 0 ${-half * 0.75} ${half * 0.85} ${half * 0.3}`} {...line} />;
    case "lake":
      return (
        <path
          d={`M ${-half * 0.9} ${half * 0.2} Q ${-half * 0.45} ${-half * 0.3} 0 ${half * 0.2} Q ${half * 0.45} ${-half * 0.3} ${half * 0.9} ${half * 0.2}`}
          {...line}
        />
      );
    case "forest":
      return <path d={`M ${-half * 0.85} 0 H ${half * 0.85} M 0 ${-half * 0.85} V ${half * 0.85}`} {...line} />;
    case "mountain":
      return <path d={`M ${-half * 0.9} ${half * 0.65} L 0 ${-half * 0.8} L ${half * 0.9} ${half * 0.65}`} {...line} />;
    case "water":
      return (
        <path
          d={`M ${-half * 0.9} ${-half * 0.15} Q ${-half * 0.45} ${-half * 0.6} 0 ${-half * 0.15} Q ${half * 0.45} ${-half * 0.6} ${half * 0.9} ${-half * 0.15} M ${-half * 0.9} ${half * 0.45} Q ${-half * 0.45} 0 0 ${half * 0.45} Q ${half * 0.45} 0 ${half * 0.9} ${half * 0.45}`}
          {...line}
        />
      );
  }
}

function BoardDefs({ uid }: { uid: string }) {
  return (
    <defs>
      <linearGradient id={`${uid}-shade`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0.55" stopColor="#241b10" stopOpacity="0" />
        <stop offset="1" stopColor="#241b10" stopOpacity="0.18" />
      </linearGradient>
      <pattern id={`${uid}-river`} width="20" height="14" patternUnits="userSpaceOnUse">
        <path d="M0 10 q5 -4 10 0 t10 0" fill="none" stroke="#d8f1f7" strokeOpacity="0.22" strokeWidth="1.2" strokeLinecap="round" />
        <path d="M-10 4 q5 -4 10 0 t10 0" fill="none" stroke="#d8f1f7" strokeOpacity="0.15" strokeWidth="1" strokeLinecap="round" />
      </pattern>
      <filter id={`${uid}-tile-shadow`} x="-8%" y="-8%" width="116%" height="116%">
        <feDropShadow dx="0" dy="1.8" stdDeviation="1.8" floodColor="#1c140c" floodOpacity="0.34" />
      </filter>
    </defs>
  );
}

function Tiles({ uid, tiles, touched }: { uid: string; tiles: TerraMysticaTile[]; touched: Map<string, string> }) {
  return (
    <g filter={`url(#${uid}-tile-shadow)`}>
      {tiles.map((tile) => {
        const at = centre(tile.q, tile.r);
        const corners = cornersAround(at);
        const key = tileKey(tile.q, tile.r);
        const meta = TERRAIN_META[tile.terrain];
        const point = toSvg(at);
        return (
          <g key={key}>
            <title>{`${key} ${meta.label}${tile.building ? `, ${BUILDING_LABEL[tile.building.type].toLowerCase()} of ${seatLabel(tile.building.owner)}` : ""}`}</title>
            <polygon points={pointList(corners)} fill={meta.fill} stroke="#2b241a" strokeOpacity={0.62} strokeWidth={1.1} strokeLinejoin="round" />
            <polygon points={pointList(corners)} fill={`url(#${uid}-shade)`} />
            {tile.terrain === "river" ? <polygon points={pointList(corners)} fill={`url(#${uid}-river)`} /> : null}
            {touched.has(key) ? (
              <polygon points={pointList(corners)} fill="none" stroke={touched.get(key)} strokeWidth={3} strokeLinejoin="round" />
            ) : null}
            <polygon points={pointList(corners)} fill="none" stroke="rgb(255 255 255 / 0.2)" strokeWidth={0.65} strokeLinejoin="round" />
            <text
              x={point.x}
              y={point.y - SCALE * 0.64}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={SCALE * 0.21}
              fontFamily="var(--font-geist-mono)"
              fill={meta.ink}
              fillOpacity={0.72}
            >
              {tile.q},{tile.r}
            </text>
            <g transform={`translate(${point.x} ${point.y + SCALE * 0.68})`}>
              <TerrainSymbol symbol={meta.symbol} color={meta.ink} size={SCALE * 0.3} strokeWidth={1.4} />
            </g>
          </g>
        );
      })}
    </g>
  );
}

export function TerraMysticaBoardSvg({
  observation,
  events,
}: {
  observation: { board: TerraMysticaTile[]; players: TerraMysticaPlayer[] };
  events: EventRecord[];
}) {
  const uid = useId().replace(/:/g, "");
  const frame = boardFrame(observation.board);
  const touched = touchedTiles(events);
  const factionBySeat = new Map(observation.players.map((player) => [player.seat, player.faction]));
  return (
    // on desktop the SVG fills its box and keeps its proportions inside it
    <svg
      viewBox={`${frame.left} ${frame.top} ${frame.width} ${frame.height}`}
      role="img"
      aria-label="Terra Mystica board"
      className="block h-auto w-full select-none @4xl:absolute @4xl:inset-0 @4xl:h-full"
      fontFamily="var(--font-geist-sans)"
    >
      <title>Terra Mystica board</title>
      <BoardDefs uid={uid} />
      <Tiles uid={uid} tiles={observation.board} touched={touched} />
      {observation.board.map((tile) =>
        tile.building ? (
          <BuildingToken
            key={tileKey(tile.q, tile.r)}
            tile={tile}
            centre={centre(tile.q, tile.r)}
            faction={factionBySeat.get(tile.building.owner) ?? ""}
          />
        ) : null,
      )}
    </svg>
  );
}

export function TerrainLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-[11px] text-muted-foreground">
      {TERRAINS.map((terrain: Terrain) => {
        const meta = TERRAIN_META[terrain];
        return (
          <span key={terrain} className="flex items-center gap-1.5">
            <span
              className="flex size-4 items-center justify-center rounded-sm border border-black/20"
              style={{ background: meta.fill }}
              title={meta.label}
            >
              <svg viewBox="-6 -6 12 12" className="size-3" aria-hidden="true">
                <TerrainSymbol symbol={meta.symbol} color={meta.ink} size={10} strokeWidth={1.6} />
              </svg>
            </span>
            <span>
              <span className="font-mono font-semibold text-foreground">{meta.letter}</span> {meta.label}
            </span>
          </span>
        );
      })}
      <span className="w-full text-[10px] text-muted-foreground/70">
        q,r labels name the hex an action refers to. Gold outlines mark the step&apos;s building, green the terrain it changed.
      </span>
    </div>
  );
}
