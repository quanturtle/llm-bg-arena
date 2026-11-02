from tabletop_arena.core import Event, PlayerId

ALICE = PlayerId(0)
BOB = PlayerId(1)


def test_public_event_is_visible_to_everyone() -> None:
    event = Event("rolled", "P1 rolled 4", {"value": 4})
    assert event.is_visible_to(ALICE)
    assert event.is_visible_to(None)
    return


def test_private_event_is_hidden_from_others_and_spectators() -> None:
    event = Event("drew", "P1 drew a 5", {"card": 5}, audience=frozenset({ALICE}))
    assert event.is_visible_to(ALICE)
    assert not event.is_visible_to(BOB)
    assert not event.is_visible_to(None)
    return


def test_event_json_lists_private_audience() -> None:
    event = Event("drew", "P2 drew a 5", audience=frozenset({BOB}))
    assert event.to_json()["audience"] == [1]
    assert Event("rolled", "x").to_json()["audience"] == "everyone"
    return
