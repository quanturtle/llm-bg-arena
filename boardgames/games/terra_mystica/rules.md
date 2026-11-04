# Terra Mystica

## Goal
Build the most victory points over six rounds. Points come from buildings, towns,
shipping and digging tracks, cult tracks, the largest connected area and leftover
resources at the end.

## Table and factions
Two to five players each play a different faction. Factions are dealt at random
in this implementation. A faction has a home terrain, starting resources,
starting cult positions, building costs and a few rules exceptions. You may only
build on your home terrain, so you must transform neighbouring terrain to expand.

This implementation uses the standard 113-tile base map, all fourteen base-game
factions and their starting resources, building costs and cost/track exceptions.
Not yet implemented: bonus cards, favor tiles, leeching power from opponents,
bridges, power conversions and faction special actions. The core economy,
terraforming, cults, towns and scoring are playable.

## Round structure
Each round has an income phase, an action phase and cleanup.
- Income: every player gains workers from dwellings, coins and power from trading
  houses, priests from temples and sanctuaries, plus the faction's base worker
  income and stronghold income. The standard base income is 1 worker (Engineers
  have none, Swarmlings have 2).
- Actions: players take one action at a time until they pass. The first player to
  pass starts the next round.
- Cleanup: the current round tile's cult bonus is paid in the next round's play
  order, then the next round's income is collected. If the bonus is spades, its
  owner chooses which reachable tiles to transform or skips them. There is no
  cult bonus after the final round. After the final round, final scoring is
  applied.

## Actions
- **Build a dwelling** on a tile reachable from one of your structures, directly
  or across up to your shipping value in river spaces. If the tile is not your
  home terrain you must pay spades to transform it first. Spades cost workers at
  your digging rate (or priests for the Darklings).
- **Transform terrain** into your home terrain without building.
- **Upgrade a structure**: dwelling to trading house; trading house to temple or
  stronghold; temple to sanctuary. A trading house costs less when an opponent's
  structure is directly adjacent.
- **Advance shipping** for 1 priest and 4 coins, gaining 2/3/4 points on the
  standard track. Shipping is not available to the Dwarves or Fakirs.
- **Advance digging** for the faction's digging cost. Darklings cannot dig and
  Fakirs stop after one step.
- **Send a priest** to an unused order space of a cult to advance 3 or 2 spaces.
  Each order space can hold only one priest for the whole game. Alternatively,
  **spend a priest to advance a cult by 1 space** without using an order space.
  Advancing past the 3rd, 5th, 7th and 10th spaces grants power. Space 10 needs a
  town key.
- **Power action**: spend charged power for a priest, two workers or seven coins.
  If Bowl III is short, you may burn Bowl II power to reach it; each step moved
  this way also removes one token from your power cycle.
- **Pass** to stop acting for the round.

## Towns and keys
Four connected structures with total power 7 form a town (three with a sanctuary).
Building or upgrading into a town awards 5 victory points, a key and the faction's
town bonus. A key lets one cult marker enter space 10. Structures already in a
town are marked and cannot found another town; building next to a town expands it.

## Scoring tiles
Each round tile scores one action: dwellings, trading houses, strongholds,
sanctuaries, spades or towns. The points are awarded immediately when the
matching action is taken. Each tile also shows a cult bonus, paid at the end of
that round.

## Final scoring
- Each cult track: 8/4/2 points for first/second/third, split evenly on ties.
- Largest connected area: 18/12/6 points, split evenly on ties.
- Leftover resources: 1 point per 3 coins, workers and priests (Alchemists get 1
  point per 2).

## Notation
Positions are axial hex coordinates written `q,r`, for example `0,0`.
- `build 0,0` — build a dwelling (transforming first if needed).
- `transform 0,0` — transform the tile into your home terrain.
- `upgrade 0,0 trading_house` — upgrade the building there.
- `shipping` / `digging` — advance that track.
- `priest fire 0` — send a priest to the Fire order space 0.
- `advance air` — spend a priest to advance Air by 1.
- `power priest` — spend power for a priest.
- `spade 0,0` — use cult-bonus spades on a reachable tile.
- `skip spade` — forfeit the rest of your cult-bonus spades.
- `pass` — stop acting this round.
