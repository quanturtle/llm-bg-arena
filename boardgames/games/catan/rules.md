# Catan

## Goal
Be first to the victory-point target (10 by default). Points come from settlements, cities, the longest road, the largest army and development cards that are worth a victory point.

## Board
- 19 hexes produce five resources: forest gives wood, hills give brick, pasture gives sheep, fields give wheat, mountains give ore. The desert gives nothing.
- Each producing hex has a number token from 2 to 12. When that number is rolled, every settlement beside the hex takes 1 of its resource and every city takes 2.
- The robber starts on the desert. It blocks production on whatever hex it occupies.
- Nine harbours sit on coastal paths. A settlement or city on either end of a harbour gives its owner a better bank rate: 3:1 for any resource from a generic harbour, or 2:1 for the named resource.

## Setup
Players place two settlements and two roads each, in snake order: P1, P2, ... then back from the last player to P1. For each placement, put a settlement on any empty intersection at least two paths away from every other building, then a road on an empty path touching that settlement. A player's second settlement immediately takes 1 resource from each producing hex beside it.

## Turn
1. **Roll two dice.** A non-7 roll produces resources for every player. A 7 produces nothing: every player holding more than 7 cards discards half their hand, rounded down, and then the active player moves the robber to a different hex.
2. **Move the robber.** Choose a hex other than the robber's current hex. If one or more other players have a building on that hex and at least one card, choose one of them; you steal one random card. You never steal from yourself. If no other player there has a card, no card is stolen.
3. **Act.** You may build, trade and play one development card, in any order, then end your turn. You may act as many times as your cards allow.

## Build costs and piece limits
| Build | Cost | Limit per player |
|---|---|---|
| Road | 1 wood, 1 brick | 15 |
| Settlement | 1 wood, 1 brick, 1 sheep, 1 wheat | 5 |
| City (upgrade one of your settlements) | 2 wheat, 3 ore | 4 |
| Development card | 1 sheep, 1 wheat, 1 ore | deck is finite |

A new road must touch one of your roads, settlements or cities. Another player's building blocks passage through its intersection. A new settlement must touch one of your roads and be at least two paths from every existing building.

## Trade
- **Bank or harbour:** give 4 of one resource for 1 of another at the normal rate, 3:1 at a generic harbour, or 2:1 at a harbour for the resource you give. The action lists your actual rate, so use that number.
- **Players:** one card for one card. Offer one resource you hold to one player for one resource they hold. That player accepts or declines, and then your turn continues. You may make at most 3 offers in a turn by default; `max_offers_per_turn` can change that limit, and 0 means unlimited. The bank and harbours never run out.

## Development cards
There are 25 cards: 14 knights, 2 Road Building, 2 Year of Plenty, 2 Monopoly and 5 victory points.
- You may play at most one development card per turn, and only after rolling.
- You may not play a card on the turn you bought it. Victory-point cards need no play: they count as soon as you draw them.
- **Knight:** move the robber and steal as on a 7. Playing 3 or more knights can win the largest army.
- **Road Building:** place two free roads, using the normal connection rules. Place them one at a time.
- **Year of Plenty:** take any two resource cards from the bank; they may be the same resource.
- **Monopoly:** take every card of one named resource from all other players.
- **Victory point:** worth 1 point immediately. It stays hidden from opponents until the end.

## Awards
- **Longest road:** 2 points to the player with at least 5 continuous paths. An opponent's building breaks a road. Ties keep the current holder; if the holder falls below 5, the award passes to the longest eligible road.
- **Largest army:** 2 points to the player who has played at least 3 knights and more than anyone else. Ties keep the current holder.

## End and scoring
The game ends as soon as any player has at least the victory-point target. Score 1 per settlement, 2 per city, 1 per victory-point card, 2 for the longest road and 2 for the largest army. The highest total wins; the game ends at the target, so ties are rare.

## Notation
Actions are written exactly as listed, with single spaces.
- `roll` — roll the dice at the start of your turn.
- `end turn` — finish your action phase.
- `settle v12` — place or build a settlement on intersection v12.
- `road e34` — place or build a road on path e34.
- `city v12` — upgrade your settlement on v12.
- `dev` — buy a development card.
- `discard wood` — discard one wood after a 7 (one card per decision).
- `robber h5 P2` — move the robber to hex h5 and steal from P2; omit `P2` when nobody there can be robbed.
- `bank 4 wood for 1 ore` — bank trade at your rate.
- `offer wood for ore to P2` — offer one card for one card.
- `accept` / `decline` — answer an offer.
- `play knight h5 P2` — play a knight, move the robber and steal; omit the victim when nobody can be robbed.
- `play roadbuilding` — play Road Building, then place free roads with `road e34`.
- `play yearofplenty wood ore` — take one wood and one ore.
- `play monopoly wood` — take all wood from the other players.

The board lists every hex (`h`), intersection (`v`) and path (`e`) with its terrain, number, building and road owner. Use those ids directly.
