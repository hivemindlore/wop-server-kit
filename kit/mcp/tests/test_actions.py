import pytest

from wop.catalog import WopError


def test_set_game_default_tffa(game, rcon):
    game.set_game("team free for all", "pad garden")
    assert rcon.sent[:7] == ["kick allbots", "set bot_minplayers 0", "set g_gametype 6", "set g_instaPad 0",
                             "set pointlimit 64", "set timelimit 16", "map wop_padgarden"]
    assert rcon.sent[7:] == [
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
    assert rcon.sent == ["map wop_padkitchen"]
    with pytest.raises(WopError, match="only work in Capture The Lolly"):
        game.change_map("wop_fridgeCTL")


def test_set_weapons_reloads_map(game, rcon):
    game.set_weapons("instapad")
    assert rcon.sent == ["set g_instaPad 1", "map wop_padgarden"]


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
