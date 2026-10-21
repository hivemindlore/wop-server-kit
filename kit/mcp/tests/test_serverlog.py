from conftest import FakeRcon

from wop import actions
from wop.server_state import read_state
from wop.serverlog import ServerLog, parse_userinfo

LINES = [
    r"ClientUserinfoChanged: 6 n\Fat^1Pad\t\2\model\fatpad\hmodel\fatpad\sc\6\hc\90\w\0\l\0\skill\ 3.00\tl\1\sl\\",
    r"ClientUserinfoChanged: 7 n\FatPad2\t\2\model\fatpad\hmodel\fatpad\sc\5\hc\90\w\0\l\0\skill\ 4.00\tl\0\sl\\",
    r"ClientUserinfoChanged: 9 n\^3dikan\t\1\model\padman\hmodel\padman\sc\2\rc\0\hc\100\w\0\l\0\tl\0\sl\\",
    "Item: 7 weapon_pumper",
]


def test_parse_userinfo():
    info = parse_userinfo(r"n\FatPad2\t\2\model\fatpad\skill\ 3.00\tl\0\sl\\")
    assert info["n"] == "FatPad2" and info["model"] == "fatpad" and info["skill"] == " 3.00"


def test_follows_log(tmp_path):
    path = tmp_path / "qconsole.log"
    path.write_bytes(("\n".join(LINES) + "\nClientDiscon").encode() + b"\0\0")
    log = ServerLog(path)
    clients = log.update()
    assert clients[7].model == "fatpad" and clients[7].skill == 4 and clients[9].skill is None
    with open(path, "ab") as f:                     # finish the half-written line
        f.write(b"nect: 6\n")
    assert 6 not in log.update()
    path.write_bytes(b"ClientUserinfoChanged: 0 n\\PAD^4MAN\\model\\padman\\skill\\ 2.00\n")  # new log
    assert set(log.update()) == {0}


def test_state_uses_log_instead_of_dumpuser(tmp_path):
    path = tmp_path / "qconsole.log"
    path.write_text("\n".join(LINES) + "\n", encoding="latin-1")
    rcon = FakeRcon()
    asked = []
    original = rcon.command
    rcon.command = lambda cmd, **kw: (asked.append(cmd), original(cmd))[1]
    state = read_state(rcon, ServerLog(path))
    fatpad2 = next(p for p in state.players if p.clean_name == "FatPad2")
    assert fatpad2.skill == 4 and fatpad2.bot_type == "FatPad"
    # only the bots missing from the log were looked up
    assert [c for c in asked if c.startswith("dumpuser")] == [f"dumpuser {n}" for n in (0, 1, 2, 3, 4, 5, 8)]


def test_batch_runs_with_one_exec(tmp_path, monkeypatch):
    monkeypatch.setenv("WOP_HOME", str(tmp_path))
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    (tmp_path / "wop").mkdir()
    path = tmp_path / "wop" / "qconsole.log"
    path.write_text("start\n", encoding="latin-1")

    class BatchRcon(FakeRcon):
        def command(self, cmd, timeout=2.0, quiet=0.3, retry=True):
            if cmd == f"exec {actions.BATCH_FILE}":
                lines = (tmp_path / "wop" / actions.BATCH_FILE).read_text().splitlines()
                with open(path, "a", encoding="latin-1") as f:
                    f.write("^1Error: Bot 'nosuchbot' not defined\n")
                    f.write(lines[-1].split(" ", 1)[1] + "\n")   # what `echo <token>` prints
            return super().command(cmd)

    rcon = BatchRcon()
    game = actions.Game(rcon, ServerLog(path))
    problems = game._run(["kick allbots", "map wop_padgarden", "addbot padman 3 red"])
    assert rcon.sent == [f"exec {actions.BATCH_FILE}"]
    batch = (tmp_path / "wop" / actions.BATCH_FILE).read_text().splitlines()
    assert batch[:3] == ["kick allbots", "map wop_padgarden", "addbot padman 3 red"]
    assert batch[3].startswith("echo WOP_MCP_DONE_")
    assert problems == ["Error: Bot 'nosuchbot' not defined"]
