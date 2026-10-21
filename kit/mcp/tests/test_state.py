from conftest import STATUS, FakeRcon

from wop.server_state import clean, parse_keyvalues, parse_status, read_state


def test_clean():
    assert clean("^4Pirate^1Pad") == "PiratePad"
    assert clean("^7F^5ATT^7Y") == "FATTY"


def test_parse_status():
    map_name, players = parse_status(STATUS)
    assert map_name == "wop_padgarden"
    assert len(players) == 10
    assert players[5].clean_name == "PiratePad" and players[5].team == "red" and players[5].bot
    assert players[7].clean_name == "FatPad2" and players[7].team == "blue"
    human = players[9]
    assert (human.clean_name, human.bot, human.score, human.ping) == ("dikan", False, 12, 35)


def test_read_state():
    state = read_state(FakeRcon())
    assert state.map == "wop_padgarden" and state.gametype == 6 and state.team_mode
    assert not state.instapad and state.maxclients == 16
    assert [p.bot_type for p in state.bots][-3:] == ["FatPad", "FatPad", "FATTY"]
    d = state.to_dict()
    assert d["slots"] == {"max": 16, "used": 10, "free": 6}
    assert d["red"][-1] == "dikan (human)" and len(d["blue"]) == 3


def test_players_team_skips_missing_client_numbers():
    # client 2 left: Players_Team only lists connected clients, in client-number order
    status = STATUS.replace("  2     0    1    0 ^5Pad^3Lilly        ^7bot                                     16384\n", "")
    info = FakeRcon().serverinfo.replace("1 1 1 1 1 1 2 2 2 1", "3 1 1 1 1 2 1 2 1")
    state = read_state(FakeRcon(status, info))
    teams = {p.num: p.team for p in state.players}
    assert teams[0] == "spectator" and teams[7] == "red" and teams[8] == "blue" and 2 not in teams


def test_parse_keyvalues():
    values = parse_keyvalues("userinfo\n--------\nskill                 3.00\nname                 FatPad2\n")
    assert values == {"skill": "3.00", "name": "FatPad2"}
