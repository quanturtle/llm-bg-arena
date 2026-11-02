from tabletop_arena.core import PlayerId, Scores


def test_tied_players_share_the_better_rank() -> None:
    scores = Scores({PlayerId(0): 7, PlayerId(1): 9, PlayerId(2): 7, PlayerId(3): 2})
    assert scores.ranks() == {
        PlayerId(0): 2,
        PlayerId(1): 1,
        PlayerId(2): 2,
        PlayerId(3): 4,
    }
    return


def test_scores_json_is_in_seat_order_with_breakdown() -> None:
    scores = Scores(
        {PlayerId(1): 3, PlayerId(0): 5},
        breakdown={PlayerId(0): {"lots": 5}},
    )
    assert scores.to_json() == [
        {"player": 0, "points": 5, "rank": 1, "breakdown": {"lots": 5}},
        {"player": 1, "points": 3, "rank": 2, "breakdown": {}},
    ]
    return
