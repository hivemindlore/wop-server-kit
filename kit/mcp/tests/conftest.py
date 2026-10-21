import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wop import actions  # noqa: E402

# Real output captured from the server (startup game: 6 red, 3 blue)
STATUS = """map: wop_padgarden
cl score ping name            address                                 rate
-- ----- ---- --------------- --------------------------------------- -----
  0     0    1    0 ^0PAD^4MAN          ^7bot                                     16384
  1     0    1    0 ^6PadGirl         ^7bot                                     16384
  2     0    1    0 ^5Pad^3Lilly        ^7bot                                     16384
  3     0    1    0 ^6Paddy^5Bell       ^7bot                                     16384
  4     0    1    0 ^6Pelv^7i^6s          ^7bot                                     16384
  5     0    1    0 ^4Pirate^1Pad       ^7bot                                     16384
  6     0    2    0 Fat^1Pad          ^7bot                                     16384
  7     0    2    0 FatPad2         ^7bot                                     16384
  8     0    2    0 ^7F^5ATT^7Y           ^7bot                                     16384
  9    12    1   35 ^3dikan             ^7192.168.0.50:27960                     25000
"""

SERVERINFO = """Server info settings:
pointlimit           64
timelimit            16
sv_hostname          Dikan server
sv_maxclients        16
g_LPS_startlives     10
g_instaPad           0
g_gametype           6
mapname              wop_padgarden
bot_minplayers       0
Players_Team         1 1 1 1 1 1 2 2 2 1
Players_Bot          1 1 1 1 1 1 1 1 1 0
"""

MODELS = {0: "padman", 1: "padgirl", 2: "padlilly", 3: "paddybell", 4: "padman/pelvis", 5: "piratepad",
          6: "fatpad", 7: "fatpad", 8: "fatpad/fatty"}


def dumpuser(num: int) -> str:
    return f"""userinfo
--------
team                 red
skill                 3.00
model                {MODELS[num]}
name                 x
"""


class FakeRcon:
    def __init__(self, status=STATUS, serverinfo=SERVERINFO):
        self.status = status
        self.serverinfo = serverinfo
        self.sent: list[str] = []

    def command(self, cmd, timeout=2.0, quiet=0.3):
        if cmd == "status":
            return self.status
        if cmd == "serverinfo":
            return self.serverinfo
        if cmd.startswith("dumpuser "):
            return dumpuser(int(cmd.split()[1]))
        self.sent.append(cmd)
        return ""

    def is_running(self, retry=False):
        return True


@pytest.fixture
def rcon():
    return FakeRcon()


@pytest.fixture
def game(rcon, monkeypatch):
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    return actions.Game(rcon, use_log=False)
