# Terra Mystica

## Goal
Build the most victory points over the configured number of rounds (six by
default). Points come from buildings, towns, shipping and digging tracks, cult
tracks, the largest connected area and leftover resources at the end.

## Table and factions
Two to five players each play a different faction. Factions are dealt at random
in this implementation. A faction has a home terrain, starting resources,
starting cult positions, building costs and a few rules exceptions. You may only
build on your home terrain, so you must transform neighbouring terrain to expand.

This implementation uses the standard 113-tile base map, all fourteen base-game
factions and their starting resources, building costs and cost/track exceptions.
Dwarves may tunnel two spaces and Fakirs may fly two spaces (three with a
stronghold), so both can build and score across rivers. Not yet implemented:
bonus cards, favor tiles, leeching power from opponents and bridges. The core
economy, terraforming, cults, towns, faction rewards and scoring are playable.

## Round structure
Each round has an income phase, an action phase and cleanup.
- Income: every player gains workers from dwellings, coins and power from trading
  houses, priests from temples and sanctuaries, plus the faction's base worker
  income and stronghold income. The standard base income is 1 worker (Engineers
  have none, Swarmlings have 2).
- Actions: players take one action at a time until they pass. The pass order is
  recorded, and the first player to pass starts the next round.
- Cleanup: the current round tile's cult bonus is paid in the next round's play
  order, then the next round's income is collected. If the bonus is spades, its
  owner chooses which reachable tiles to transform or skips them. There is no
  cult bonus after the final round. After the final round, final scoring is
  applied.

## Actions
- **Build a dwelling** on a tile reachable from one of your structures, directly
  or across up to your shipping value in river spaces. Dwarves instead reach two
  spaces and Fakirs two (three with a stronghold), ignoring rivers. A tunnel
  costs the Dwarves 2 workers, or 1 with a stronghold; a carpet flight costs the
  Fakirs 1 priest. Either scores 4 victory points. If the tile is not your home
  terrain you must pay spades to transform it first. Spades cost workers at your
  digging rate (or priests for the Darklings).
- **Transform terrain** into your home terrain, or stop at any terrain on the
  wheel. Each step costs a spade. Dwarves and Fakirs may use their tunnel or
  flight here too, paying the same cost and scoring the same 4 points.
- **Upgrade a structure**: dwelling to trading house; trading house to temple or
  stronghold; temple to sanctuary. A trading house costs less when an opponent's
  structure is directly adjacent.
- **Advance shipping** for 1 priest and 4 coins, gaining 2/3/4 points on the
  standard track. Mermaids have a longer track: they begin one step ahead and
  earn 2/3/4/5. Shipping is not available to the Dwarves or Fakirs.
- **Advance digging** for the faction's digging cost. Darklings cannot dig and
  Fakirs stop after one step.
- **Send a priest** to an unused order space of a cult. Order space 0 advances 3
  spaces; spaces 1-3 advance 2. A priest may take a space even when its owner
  cannot advance that track, which blocks it for everyone else. Each order space
  can hold only one priest for the whole game. Alternatively, **spend a priest to
  advance a cult by 1 space** without using an order space. Reaching spaces 3, 5,
  7 and 10 grants 1, 2, 2 and 3 power. Space 10 needs a town key, and only one
  player may stand there.
- **Power action**: each kind may be used once per round by all players together.
  A priest costs 3 power, two workers 4 power, seven coins 4 power, one spade
  4 power and two spades 6 power. After a spade action transforms a tile to your
  home terrain, you may build a dwelling there. If Bowl III is short, you may
  burn Bowl II power to reach it; each step moved this way also removes one token
  from your power cycle.
- **Pass** to stop acting for the round.

## Towns and keys
Four directly adjacent structures with total power 7 form a town (three with a
sanctuary). Indirect adjacency, including across rivers or by tunneling, does
not join a town. The Mermaids may choose one river space to ignore; a normal
build or upgrade does not join across a river. Building or upgrading into a town
awards a key, the faction's town bonus and a choice of one of the remaining town
tiles: 5 VP and 6 coins; 7 VP and 2 workers; 9 VP and 1 priest; 6 VP and 8 power;
or 8 VP and one step on each cult track. There are at most 10 towns. A key lets
one cult marker enter space 10. Structures already in a town are marked and
cannot found another town; building next to a town expands it.

## Scoring tiles
Each round tile scores one action: dwellings (2 points), trading houses (3),
strongholds or sanctuaries (5), spades (2) or towns (5). The spade tile is never
placed in rounds 5 or 6. The points are awarded immediately when the matching
action is taken. Each tile also shows a cult bonus, paid at the end of that round;
the final round's bonus is shown but never paid. A cult-bonus spade budget belongs
to the player it is announced for; the text and observation show it until that
player uses or skips it. A cult-bonus spade may transform a tile part of the way,
stopping at any terrain on the wheel; the player spends up to the budget and keeps
whatever is left. Spades may be split across tiles and aimed at any terrain on
the wheel. Halflings score 1 victory point for every spade they receive. Priests
are limited to each faction's supply of seven; priests sent to cult order spaces
still count against that supply.

## Final scoring
- Each cult track: 8/4/2 points for first/second/third, split evenly on ties.
- Largest connected area: 18/12/6 points, split evenly on ties. Shipping, Dwarves'
  tunneling and Fakirs' carpet flight all connect structures for this score.
- Leftover resources: 1 point per 3 coins, workers, priests and Bowl III power
  (Alchemists get 1 point per 2). Power in Bowl II is burned and scores nothing.

## Notation
Positions are axial hex coordinates written `q,r`, for example `0,0`.
- `build 0,0` — build a dwelling (transforming first if needed).
- `build 0,0 river 1,1` — as the Mermaids, ignore river 1,1 for this town.
- `transform 0,0` — transform the tile into your home terrain.
- `transform 0,0 to forest` — transform it to another terrain on the wheel.
- `upgrade 0,0 trading_house` — upgrade the building there.
- `upgrade 0,0 temple river 1,1` — as the Mermaids, upgrade and ignore river 1,1.
- `shipping` / `digging` — advance that track.
- `priest fire 0` — send a priest to the Fire order space 0.
- `advance air` — spend a priest to advance Air by 1.
- `stronghold fire` — take the Darklings' stronghold cult step.
- `power priest` — spend power for a priest or another power action.
- `spade 0,0` — use cult-bonus spades on a reachable tile.
- `spade 0,0 to forest` — aim them at a chosen terrain.
- `skip spade` — forfeit the rest of your cult-bonus spades.
- `town 0` — take town tile 0.
- `alchemist vp` / `alchemist coins` — the Alchemists' 1 VP for 1 coin or 2 coins for 1 VP.
- `pass` — stop acting this round.
