import pytest

from wop.catalog import (
    ALL_MAPS, BOTS, GAMEMODES, WopError, check_map_fits, resolve_bot, resolve_gamemode, resolve_map, resolve_team,
)


def test_counts():
    assert len(ALL_MAPS) == 46 == len(set(ALL_MAPS))
    assert len(BOTS) == 29
    assert len({b.model for b in BOTS}) == 29
    assert [m.id for m in GAMEMODES] == [0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11]


@pytest.mark.parametrize("mode", GAMEMODES, ids=lambda m: m.key)
def test_defaults_are_valid(mode):
    check_map_fits(mode.default_map, mode)
    for name in mode.default_red + mode.default_blue + mode.default_bots:
        resolve_bot(name)
    assert bool(mode.default_red) == mode.team


@pytest.mark.parametrize("text,expected", [
    ("wop_padgarden", "wop_padgarden"),
    ("pad garden", "wop_padgarden"),
    ("Padgarden Night", "wop_padgarden_night"),
    ("PADBASECTL", "wop_padbaseCTL"),
    ("padcrash dm17", "wop_padcrash_dm17"),
])
def test_resolve_map(text, expected):
    assert resolve_map(text) == expected


def test_resolve_map_uses_mode_suffix():
    assert resolve_map("padbase", resolve_gamemode("ctl")) == "wop_padbaseCTL"
    assert resolve_map("padgarden", resolve_gamemode("big balloon")) == "wop_padgardenBB"
    assert resolve_map("padgarden", resolve_gamemode("tffa")) == "wop_padgarden"


def test_resolve_map_suggests():
    with pytest.raises(WopError, match="wop_padkitchen"):
        resolve_map("padkitchn")


@pytest.mark.parametrize("text,mode_id", [
    ("ctl", 8), ("Capture the flag", 8), ("team ffa", 6), ("Free For All Team", 6), ("ffa", 0),
    ("instagib", None), (11, 11), ("4", 4), ("freeze", 7), ("one lolly", 9), ("1v1", 1),
])
def test_resolve_gamemode(text, mode_id):
    if mode_id is None:
        with pytest.raises(WopError):
            resolve_gamemode(text)
    else:
        assert resolve_gamemode(text).id == mode_id


def test_resolve_bot():
    assert resolve_bot("fatty").name == "FATTY"
    assert resolve_bot("pad-ra").name == "Pad-RA"
    assert resolve_bot("Pad RA").name == "Pad-RA"
    with pytest.raises(WopError, match="FatPad"):
        resolve_bot("fatpaad")


def test_map_must_fit_mode():
    with pytest.raises(WopError, match="CTL"):
        check_map_fits("wop_padgarden", resolve_gamemode("ctl"))
    with pytest.raises(WopError, match="only work in Capture The Lolly"):
        check_map_fits("wop_padbaseCTL", resolve_gamemode("tffa"))
    check_map_fits("wop_padatticLPS", resolve_gamemode("ffa"))


def test_resolve_team():
    assert resolve_team("Red Pads") == "red"
    assert resolve_team("blue noses") == "blue"
    assert resolve_team("spec") == "spectator"
    with pytest.raises(WopError):
        resolve_team("green")
