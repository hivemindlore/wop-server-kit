import pytest

from wop.catalog import WopError


def test_set_game_default_tffa(game, rcon):
    game.set_game("team free for all", "pad garden")
    assert rcon.sent[:8] == ["kick allbots", "set bot_minplayers 0", "set g_gametype 6", "set g_instaPad 0",
                             "set pointlimit 64", "set timelimit 16", 'set wop_maplist "wop_padgarden"',
                             "map wop_padgarden"]
    assert rcon.sent[8:] == [
        "addbot PADMAN 3 red", "addbot PadGirl 3 red", "addbot PadLilly 3 red", "addbot PaddyBell 3 red",
        "addbot Pelvis 3 red", "addbot PiratePad 3 red",
        "addbot FatPad 3 blue", 'addbot FatPad 3 blue 0 "FatPad2"', "addbot FATTY 3 blue",
    ]


def test_set_game_ctl_instapad_custom_teams(game, rcon):
    result = game.set_game("ctl", "padbase", "instapad", red=["padman", {"name": "padgirl", "skill": 5}],
                           blue=["fatpad", "fatpad", "fatpad"], skill=2, timelimit=10)
    assert "set g_instaPad 1" in rcon.sent and "set timelimit 10" in rcon.sent and "map wop_padbaseCTL" in rcon.sent
    adds = [c for c in rcon.sent if c.startswith("addbot")]
    assert adds == ["addbot PADMAN 2 red", "addbot PadGirl 5 red", "addbot FatPad 2 blue",
                    'addbot FatPad 2 blue 0 "FatPad2"', 'addbot FatPad 2 blue 0 "FatPad3"']
    assert "state" in result


def test_set_game_solo_has_no_teams(game, rcon):
    game.set_game("ffa", bots=["padman", "padman"])
    assert [c for c in rcon.sent if c.startswith("addbot")] == ["addbot PADMAN 3 free",
                                                                'addbot PADMAN 3 free 0 "PADMAN2"']


def test_set_game_without_bots(game, rcon):
    game.set_game("ctl", no_bots=True)
    assert "kick allbots" in rcon.sent and not [c for c in rcon.sent if c.startswith("addbot")]


def test_set_game_bots_balanced_in_team_mode(game, rcon):
    game.set_game("freeze tag", bots=["padman", "padgirl", "padking", "fatty"])
    teams = [c.split()[3] for c in rcon.sent if c.startswith("addbot")]
    assert teams == ["red", "blue", "red", "blue"]


def test_set_game_keeps_current_bots(game, rcon):
    game.set_game("ctl", keep_current_bots=True)
    adds = [c for c in rcon.sent if c.startswith("addbot")]
    assert len(adds) == 9 and 'addbot FatPad 3 blue 0 "FatPad2"' in adds


def test_set_game_rejects_wrong_map(game, rcon):
    with pytest.raises(WopError, match="CTL"):
        game.set_game("ctl", "padgarden night")
    assert rcon.sent == []


def test_set_game_slot_limit(game, rcon):
    with pytest.raises(WopError, match="16 slots"):
        game.set_game("ffa", bots=["padman"] * 16)  # plus 1 human = 17
    assert rcon.sent == []


def test_change_map_keeps_mode(game, rcon):
    game.change_map("pad kitchen")
    assert rcon.sent == ["nextmap", "map wop_padkitchen"]   # no map loop running: nothing to keep
    with pytest.raises(WopError, match="only work in Capture The Lolly"):
        game.change_map("wop_fridgeCTL")


def test_set_weapons_reloads_map(game, rcon):
    game.set_weapons("instapad")
    assert rcon.sent == ["nextmap", "set g_instaPad 1", "map wop_padgarden"]


def test_add_bots_balances_and_names(game, rcon):
    game.add_bots(["fatpad", "padking"])
    # red has 6 bots + 1 human, blue 3: both go to blue; FatPad and FatPad2 exist already
    assert rcon.sent == ['addbot FatPad 3 blue 0 "FatPad3"', "addbot PadKing 3 blue"]


def test_remove_bots(game, rcon):
    game.remove_bots(["FatPad2", "fatty", "nobody"])
    assert rcon.sent == ["clientkick 7", "clientkick 8"]


def test_move_bot_is_readded(game, rcon):
    game.move_player("FatPad2", "red")
    assert rcon.sent == ["clientkick 7", 'addbot FatPad 3 red 0 "FatPad2"']


def test_move_human_uses_forceteam(game, rcon):
    game.move_player("dikan", "blue")
    assert rcon.sent == ["forceteam 9 blue"]


def test_find_player_ambiguous(game):
    with pytest.raises(WopError, match="more than one"):
        game.move_player("pad", "blue")


def test_console_command_blocklist(game, rcon):
    for cmd in ["quit", "  QUIT", "killserver", "rconpassword x", "set rconpassword x", "exec server-friends.cfg"]:
        with pytest.raises(WopError):
            game.run_console_command(cmd)
    game.run_console_command("g_gravity 400")
    assert rcon.sent == ["g_gravity 400"]


def test_sanitize_message(game, rcon):
    game.send_message('hi"; quit')
    assert rcon.sent == ["ssay hi quit"]


def test_messages_use_wops_own_commands(game, rcon):
    """The engine's say/tell send a chat line WoP 1.7.0 doesn't show; its game code has ssay/stell."""
    game.send_message("Dinner is ready!")
    game.send_message("psst", player="FATTY")
    assert rcon.sent == ["ssay Dinner is ready!", "stell 8 psst"]


@pytest.mark.parametrize("typed,sent", [
    ("say hello all", "ssay hello all"),
    ("SAY hi", "ssay hi"),
    ("tell 3 hi", "stell 3 hi"),
    ("sayto x", "sayto x"),          # not the word say
    ("ssay hi", "ssay hi"),
    ("g_gravity 400", "g_gravity 400"),
])
def test_console_say_becomes_ssay(game, rcon, typed, sent):
    game.run_console_command(typed)
    assert rcon.sent == [sent]


def test_spawn_protection_needs_the_kits_game_code(game, rcon):
    with pytest.raises(WopError, match="always uses 6 seconds"):
        game.set_spawn_protection(False)
    assert rcon.sent == []


def test_spawn_protection_on_and_off(rcon, monkeypatch):
    from conftest import SERVERINFO, FakeRcon
    from wop import actions
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    rcon = FakeRcon(serverinfo=SERVERINFO.replace("g_instaPad           0", "g_instaPad           1")
                    + "g_spawnProtect       6\n")
    game = actions.Game(rcon, use_log=False)
    assert game.state().to_dict()["spawn_protection_seconds"] == 6
    result = game.set_spawn_protection(False)
    game.set_spawn_protection(True)
    assert rcon.sent == ["set g_spawnProtect 0", "set g_spawnProtect 3"]
    assert "off" in result["result"] and "It only matters" not in result["result"]


class LoopRcon:
    """A server where a map loop runs (it answers the nextmap and wop_maplist questions)."""

    def __init__(self, rcon, nextmap="vstr wop_rot2", maplist="wop_padgarden wop_padkitchen wop_padship"):
        self.rcon, self.values = rcon, {"nextmap": nextmap, "wop_maplist": maplist}

    def command(self, cmd, timeout=2.0, quiet=0.3):
        if cmd in self.values:
            return f'"{cmd}" is:"{self.values[cmd]}^7" default:""'
        return self.rcon.command(cmd, timeout, quiet)

    def is_running(self, retry=False):
        return True


def test_set_game_with_a_map_loop(game, rcon):
    result = game.set_game("ctl", maps=["padbase", "journey", "wop_padbaseCTL", "fridge"], bots=["padman"])
    sent = rcon.sent
    first = sent.index("map wop_padbaseCTL")
    assert sent[first - 4:first] == [
        'set wop_rot0 "map wop_padbaseCTL; set nextmap vstr wop_rot1"',
        'set wop_rot1 "map wop_journeyCTL; set nextmap vstr wop_rot2"',
        'set wop_rot2 "map wop_fridgeCTL; set nextmap vstr wop_rot0"',
        'set wop_maplist "wop_padbaseCTL wop_journeyCTL wop_fridgeCTL"',
    ]
    assert sent[first + 1] == "set nextmap vstr wop_rot1"           # after the map: loading resets it
    assert sent[first + 2].startswith("addbot PADMAN")
    assert "padbaseCTL, journeyCTL and fridgeCTL in a loop" in result["result"]


def test_map_loop_maps_must_fit_the_mode(game):
    with pytest.raises(WopError, match="Lolly modes need a CTL map"):
        game.set_game("ctl", maps=["padbase", "padgarden"])
    with pytest.raises(WopError, match="up to 16"):
        from wop.catalog import GAMEMODES
        game.set_game("ffa", maps=[m for m in GAMEMODES[0].maps][:17])


def test_reloading_a_map_keeps_the_loop(game, rcon):
    game.rcon = LoopRcon(rcon)
    game.set_weapons("instapad")
    assert rcon.sent == ["set g_instaPad 1", "map wop_padgarden", "set nextmap vstr wop_rot2"]
    rcon.sent.clear()
    game.change_map("pad kitchen")
    assert rcon.sent == ["map wop_padkitchen", "set nextmap vstr wop_rot2"]


def test_map_rotation(game, rcon):
    game.rcon = LoopRcon(rcon)
    assert game.map_rotation() == ["wop_padgarden", "wop_padkitchen", "wop_padship"]
    game.rcon = LoopRcon(rcon, maplist="nonsense")
    assert game.map_rotation() == []


def test_set_game_with_weapons_and_spawn_protection(rcon, monkeypatch):
    from conftest import FakeRcon
    from wop import actions
    kit_code = FakeRcon(serverinfo=rcon.serverinfo + "g_spawnProtect       3\n")
    game = actions.Game(kit_code, use_log=False)
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    game.set_game("ffa", weapons="instapad", spawn_protection=False, bots=["padman"])
    sent = kit_code.sent
    assert "set g_instaPad 1" in sent
    assert sent.index("set g_spawnProtect 0") < sent.index("map wop_padship")


def test_spawn_protection_needs_the_kits_game_code(game, rcon):
    game.set_game("ffa", spawn_protection=True, bots=["padman"])
    assert not [c for c in rcon.sent if "g_spawnProtect" in c]   # plain WoP 1.7.0: always 6 seconds
