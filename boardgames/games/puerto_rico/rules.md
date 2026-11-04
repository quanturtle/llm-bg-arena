# Puerto Rico

## Goal
Build the most victory points. Points come from shipping goods to Europe (victory point chips), from buildings, and from five large violet buildings that pay bonuses at the end. The game ends at the end of a round when the victory point supply runs out, the colonist supply runs out, or a player fills all 12 city spaces.

## Setup
- Each player starts with doubloons equal to the number of players minus one (2 for 3 players, 3 for 4, 4 for 5), one starting plantation (indigo for the first players in governor order, corn for the rest), and no buildings.
- The colonist ship starts with one colonist per player. The colonist supply holds 55/75/95 colonists for 3/4/5 players.
- The victory point supply holds 75/100/122 chips for 3/4/5 players.
- The three cargo ships have capacities 4, 5, 6 (3 players), 5, 6, 7 (4 players) or 6, 7, 8 (5 players).
- The governor chooses first. Role cards are chosen once each round in governor order; after every player has chosen, the round ends and the governorship passes clockwise.

## Roles and privileges
- **Settler:** take a face-up plantation. Privilege: the Settler may take a quarry instead. A player with an active Construction Hut may also take a quarry. Unchosen face-up plantations wait in a discard pile; when the deck cannot refill the row, the discard pile is shuffled into a new deck.
- **Mayor:** colonists from the ship are distributed round-robin starting with the Mayor. Privilege: the Mayor takes one extra colonist from the supply. Then each player places every new colonist on an empty circle before moving any existing colonist.
- **Builder:** build one building. Privilege: the Builder pays one doubloon less. Each active quarry also reduces a building's cost by one, up to the building's victory point value.
- **Craftsman:** every player produces goods. Privilege: the Craftsman may take one extra producible good from the supply.
- **Trader:** sell one good to the trading house. Privilege: the Trader gets one extra doubloon. The trading house holds at most four goods; when it is full at the end of the Trader phase its goods return to the supply. An Office lets its owner sell a type already present.
- **Captain:** load goods on the cargo ships. Privilege: the Captain gets one extra victory point on their first shipment of the phase. A Harbor gives one extra victory point on every shipment. A Wharf may load all goods of one type once per phase; goods shipped by Wharf return to the supply.
- **Prospector:** take one doubloon and no action. In a 4-player game there is one Prospector; in a 5-player game there are two.

## Production and shipping
- Each occupied production building needs matching occupied plantations: a small building needs one colonist and one matching plantation, a large building needs up to its colonist capacity and matching plantations. Corn needs no building; every occupied corn plantation produces one corn.
- Production is limited by the goods supply. A Factory gives 1/2/3/5 doubloons when 2/3/4/5 different goods types are produced.
- Each cargo ship carries only one good type. Load as much of a good as the ship's remaining space allows. Each good shipped gives one victory point chip. A full ship's goods return to the supply when the Captain phase ends; partially filled and empty ships stay as they are.
- After shipping, each player keeps one good of each type. A Small Warehouse keeps all of one type; a Large Warehouse keeps all of two types. Excess goods return to the supply.

## Buildings
| Building | Cost | VP | Colonists | Effect |
|---|---|---|---|---|
| Small Indigo Plant | 1 | 1 | 1 | Produces indigo |
| Indigo Plant | 3 | 2 | 3 | Produces indigo |
| Small Sugar Mill | 2 | 1 | 1 | Produces sugar |
| Sugar Mill | 4 | 2 | 3 | Produces sugar |
| Tobacco Storage | 5 | 3 | 3 | Produces tobacco |
| Coffee Roaster | 6 | 3 | 2 | Produces coffee |
| Small Market | 1 | 1 | 1 | +1 doubloon when selling |
| Hacienda | 2 | 1 | 1 | Draw an extra plantation when taking one |
| Construction Hut | 2 | 1 | 1 | May take a quarry instead of a plantation |
| Small Warehouse | 3 | 1 | 1 | Keep all of one good type after shipping |
| Hospice | 4 | 2 | 1 | Colonize a taken plantation immediately |
| Office | 5 | 2 | 1 | May sell a good type already in the trading house |
| Large Market | 5 | 2 | 1 | +2 doubloons when selling |
| Large Warehouse | 6 | 2 | 1 | Keep all of two good types after shipping |
| Factory | 7 | 3 | 1 | Bonus doubloons for producing several goods types |
| University | 8 | 3 | 1 | Place a colonist on a newly built building |
| Harbor | 8 | 3 | 1 | +1 victory point on every shipment |
| Wharf | 9 | 3 | 1 | Load all goods of one type once per phase |
| Guild Hall | 10 | 4 | 1 | +1 per small production building, +2 per large |
| Residence | 10 | 4 | 1 | 4 VP plus 1 per occupied island space over 9 |
| Fortress | 10 | 4 | 1 | 1 VP per 3 colonists on your player board |
| Customs House | 10 | 4 | 1 | 1 VP per 4 victory point chips |
| City Hall | 10 | 4 | 1 | 1 VP per violet building owned |

The five large violet buildings take two city spaces each; all other buildings take one. A player may own only one copy of each building. When a building's colonist circle is filled, its effect is active.

## End and scoring
Score victory point chips, the printed points of every building, and the bonuses of active Guild Hall, Residence, Fortress, Customs House and City Hall. The highest total wins. Ties go to the player with the most doubloons plus goods; if still tied, the player closest to the governor in order wins.

## Notation
Actions are written exactly as listed, with single spaces.
- `role settler` — choose a role (settler, mayor, builder, craftsman, trader, captain, prospector, prospector_2).
- `take indigo` — take a face-up indigo plantation.
- `take quarry` — take a quarry.
- `hacienda` — draw an extra plantation with the Hacienda.
- `pass` — take no action or decline a privilege.
- `build small_indigo_plant` — build a building by its table name.
- `privilege indigo` — take an extra indigo as the Craftsman.
- `sell indigo` — sell one indigo to the trading house.
- `ship indigo s1` — load indigo on cargo ship 1 (s1, s2 or s3).
- `wharf indigo` — load all indigo on your Wharf.
- `place plantation 0` — place a colonist on plantation 0.
- `place building 0` — place a colonist on building 0.
- `place quarry` — place a colonist on a quarry.
- `pick plantation 0` — pick up a colonist from plantation 0.
- `pick building 0` — pick up a colonist from building 0.
- `pick quarry` — pick up a colonist from a quarry.
- `finish` — finish your Mayor placements.
- `discard indigo sugar` — keep goods after shipping; list the types your warehouses protect (none if you have no warehouse).
