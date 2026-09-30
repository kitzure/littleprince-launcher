#!/usr/bin/env python3
"""
Little Prince Launcher (macOS) - the window that runs everything.

Same job as Start_Server_GUI.pyw on Windows: start the local servers, show what
is running, say which of the four games are here, fetch the ones that are not,
and open the games. The difference is that macOS needs no hosts redirect and no
port 80 (the browser is pointed at a local relay instead), so nothing here asks
for administrator rights.

The WINDOW is not drawn here: it is launcher_ui.py at the root of the pack, the
same window the Windows launcher (Start_Server_GUI.pyw) draws.  This file is the
macOS half - the backend the window asks about the servers, the Flash runtime and
the game files - so a change to the window cannot land on one platform only.

Servers started:
  lpo/server.py            Little Prince Online mirror, accounts website, profile
  fake_server.py 8081      the CD games (LP1/LP2/LP3) and the portal page
  macos/mac_relay.py 8900  routes the games' absolute addresses to the two above

Game files:
  The package carries no game data of its own.  The status panel reports the
  Little Prince Online client and the three cloud games as `ready`, `partial
  (n of m files)` or `not downloaded`, and one button fetches whatever the user
  picks.  The checks and the fetches are lpo/fetch_client.py and
  lpo/fetch_cloud.py - the same tools the Windows launcher drives.

If tkinter is missing (Apple's command line Python has no Tk), the launcher
still starts everything and prints the addresses instead of drawing a window.
"""

import contextlib
import importlib.util
import io
import json
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNTIME = HERE / 'runtime'
ONLINE_PORT = 8950
CLOUD_PORT = 8081
RELAY_PORT = 8900
MP_PORT = 8443             # LAN multiplayer relay (lpo/mp_relay.py)
PLUGIN = RUNTIME / 'PepperFlashPlayer.plugin'
PLUGIN_BIN = PLUGIN / 'Contents' / 'MacOS' / 'PepperFlashPlayer'

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))          # launcher_ui.py lives at the pack root
import setup_runtime                                     # noqa: E402  (same folder)
import launcher_ui                    # noqa: E402  the window both platforms draw


# ── the wording ──────────────────────────────────────────────────────────────
# Everything this backend says is named here, so the EN/ZH badge in the title
# strip switches the launcher's own words and not just the games behind it.  The
# window in launcher_ui.py has none of these words of its own; it re-reads them
# from the hooks on every refresh.  The Chinese follows the Windows launcher's
# table (Start_Server_GUI.pyw) wherever the two say the same thing - 選單, 伺服器,
# 啟動, 停止, 下載遊戲檔案, 帳號網站, 使用者, 官方伺服器 - so both launchers read
# the same.  The four game titles in games() are the game's own data, not the
# launcher's wording, so they are deliberately not in here.

TR = {
    "en": {
        # the servers, the browser and the log
        "port_running": "%s: already running on port %d",
        "srv_starting": "starting %s: %s",
        "srv_failed": "%s failed to start: %s",
        "srv_stopped": "stopped %s",
        "no_browser": "The launcher's browser is not set up yet - press \"Set up Flash "
                      "runtime\". It is the only browser that routes the game's own "
                      "server names back to this machine.",
        "no_plugin": "The Flash runtime is not set up yet - press \"Set up Flash "
                     "runtime\" first.",
        "opening": "opening %s",
        "no_chromium": "could not start Chromium: %s",
        "play_real": "opening the real-Flash page in the launcher's browser "
                     "(routed through the local relay)",
        "play_ruffle": "the Flash runtime is not set up - opening the Ruffle player in the "
                       "launcher's browser, which routes the game's own server names to this "
                       "machine (press \"Set up Flash runtime\" for real Flash)",
        "opened": "opened %s",
        "srv_outside": "the online world server was started outside this window - "
                       "press \"Stop servers\" then \"Start servers\" so it picks up "
                       "the new game files.",
        "restarting": "online world: restarting so it serves the new game files",
        # the game files: one state per game
        "pkg_client_missing": "lpo/fetch_client.py is missing from the package",
        "pkg_cloud_missing": "lpo/fetch_cloud.py is missing from the package",
        "check_short": "could not check (%s)",
        "not_downloaded": "not downloaded",
        "partial_files": "partial (%d of %d files)",
        "ready": "ready",
        "ready_n_files": "ready - %d files on this machine",
        "stale_files": " - the CD's client files are here (%s); the server replaces them "
                       "with the publisher's when it starts",
        "all_here": "all four games are here",
        "not_here_yet": "not here yet: ",
        "check_failed": "could not check the game files: %s",
        "gn_LPO": "Little Prince Online client",
        "gn_LP1": "LP1 cloud game",
        "gn_LP2": "LP2 cloud game",
        "gn_LP3": "LP3 cloud game",
        # the downloads
        "lpo_nothing": "LPO: nothing to fetch",
        "lpo_fetching": "LPO: fetching %d file(s) from the publisher into %s",
        "lpo_in_place": "LPO: %d of %d files in place (%d new, %d failed, %.0f MB)",
        "failed_rel": "   failed: %s - %s",
        "cloud_nothing": "%s: nothing to fetch - the files are complete",
        "cloud_fetching": "%s: fetching %d file(s), about %.0f MB, from the publisher",
        "cloud_in_place": "%s: %d of %d in place, %d could not be fetched",
        "failed_why": "   failed: %s (%s)",
        "cloud_left": "%s: %d file(s) still missing - run it again to carry on",
        "cloud_check_failed": "%s: could not check the mirror (%s)",
        "downloading": "Downloading...",
        "dl_running": "a download is already running - let it finish first",
        "dl_starting": "%s: starting...",
        "dl_broken": "%s: the download stopped: %s",
        "dl_progress": "%s: %d of %d files (%.0f%%)  %s",
        "dl_mb": "%s: %.1f MB",
        "dl_complete": "the game files are complete",
        "dl_incomplete": "the files are not complete yet - press Download "
                         "again to carry on",
        # the questions the downloads ask
        "ask_lpo": "Fetch the missing Little Prince Online game files from the "
                   "publisher?\n\nAbout %.0f MB, into\n%s\n\n"
                   "Files that are already there are skipped, so it carries on from "
                   "where it stopped.",
        "ask_cd": "Fetch the %d missing file(s) of %s from the publisher?\n\n"
                  "About %.0f MB, fetched once, into\n%s",
        "find_ask": "The Little Prince Online game files are not in this package, and they "
                    "are\nnot in any folder this launcher looks in.\n\n"
                    "Yes  -  download the official files now (about %.0f MB, once)\n"
                    "No  -  I already have the game, let me point at its folder\n"
                    "Cancel  -  not now",
        "find_title": "Find the Little Prince Online folder",
        "no_files_cancel": "LPO: no game files here - cancelled",
        "no_folder_cancel": "LPO: no folder chosen - cancelled",
        "no_swf": "No .swf files in that folder.\n\n"
                  "Pick the folder that holds index.swf and login.swf.",
        "folder_saved": "game folder: %s (remembered in lpo/game_dir.txt)",
        "still_checking": "%s: still checking the game files - press again in a moment",
        "already_here": "%s: already here (%s) - nothing to download",
        "dl_cancelled": "%s: download cancelled",
        "online_client": "the online client: %s",
        "picker_sub": "Only the files a game is missing are fetched; a game that is already "
                      "here is left alone.",
        # the window's own hooks
        "word_running": "Servers running",
        "word_stopped": "Servers stopped",
        "t_online": "online world",
        "t_cd": "CD games",
        "t_relay": "Flash relay",
        "t_mp": "multiplayer",
        "con_accounts": "accounts",
        "con_mods": "mods",
        "t_answers": "answers",
        "t_no_answer": "no answer",
        "t_item": "%s :%d %s",
        "t_sep": " - ",
        "t_ready_n": "%d of %d game files ready",
        "t_prefix": "connection test: ",
        "nothing_to_revert": "nothing to revert on macOS - the launcher never touches /etc/hosts",
        "s_online": "online",
        "s_cd": "cd games",
        "s_relay": "relay",
        "s_mp": "multiplayer",
        "s_flash": "flash runtime",
        "s_files": "game files",
        "v_on": "on :%d",
        "v_stopped": "stopped",
        "v_not_set_up": "not set up",
        "v_checking": "checking...",
        "v_ready_n": "%d of %d ready",
        "footer": "Log in with any name you like: this is a local mirror of the game.  "
                  "No administrator rights are needed - nothing here touches the hosts file.",
        "close_ask": "Stop the local servers as well?",
        "checking_games": "checking the game files...",
        "games_note": "game files: %s",
        "starting_up": "starting up",
        "play_online": "Play online world",
        "play_cd": "CD %s",
        "play_cd_row": "Play CD %s",
        "menu": "Menu",
        "sec_servers": "SERVERS",
        "server_start": "Start servers",
        "server_stop": "Stop servers",
        "sec_cd": "CD GAMES",
        "sec_files": "GAME FILES",
        "sec_user": "USER",
        "dn_files": "Download the game files",
        "check_again": "Check again",
        "setup_flash": "Set up Flash runtime",
        "mods": "Mods",
        "accounts": "Accounts website",
        "open_client_folder": "Open the Little Prince Online folder",
        "no_open": "could not open %s (%s)",
        "setup_running": "setting up the Flash runtime...",
        "done": "done.",
        "setup_failed": "setup failed: %s",
        # ── the avatar art: the one thing the pack does not carry ─────────────
        # lpo/avatar.py draws the player's own character with Pillow.  Neither
        # platform ships an interpreter with it (both run a python.org build), so
        # the accounts page shows an empty character on a machine without it -
        # this is where that machine gets it back, in one click.
        "s_avatar": "character art",
        "v_no_pillow": "needs Pillow",
        "v_art_broken": "cannot be drawn",
        "install_pillow": "Install Pillow",
        "pillow_missing": "character art: %s  -  press \"Install Pillow\" in the menu "
                          "(or the button on the left) to do it from here.",
        "pillow_running": "character art: installing Pillow - %s",
        "pillow_ok": "character art: Pillow is installed (%s) - the accounts page draws "
                     "the character again (reload it if it is already open)",
        "pillow_failed": "character art: the install did not work (%s) - install it "
                         "yourself with:  %s",
        "pillow_broken": "character art: %s  -  the avatar dataset this picture needs "
                         "cannot be used here, so installing Pillow is not the fix",
        "pillow_busy": "a Pillow install is already running - let it finish first",
        # what is printed before (or without) a window
        "startup_1": "the online world listens on port %d (accounts page /web, mods /mods)",
        "startup_2": "CD games on port %d, Flash relay on %d, multiplayer relay on %d",
        "startup_3": "the Flash runtime is not set up yet - press \"Set up Flash "
                     "runtime\" (one download) for real Flash",
        "startup_tk": "Tk %s is the old system build, so this window may stay "
                      "blank - the games work the same, or run with --console.",
        "startup_start": "starting the servers - this window can stay open while you play.",
        "tk_note": "NOTE: Tk %s is the old system build. If the window comes up empty,\n"
                   "      run:  %s macos/launcher_gui.py --console\n"
                   "      or install the python.org build, which ships Tk 8.6.",
        "con_title": "Little Prince Launcher (macOS) - console mode",
        "con_no_tk": "tkinter is not available, so there is no window. Everything still runs.\n",
        "addresses": "\nAddresses:",
        "con_open": "\nOpening the online world in the Flash browser. Ctrl-C stops the servers.",
        "no_tk_notice": "no tkinter here - running in this window instead.",
        "no_window_notice": "\nthe window could not be built, so the launcher is running here "
                            "instead.",
    },
    "zh": {
        # the servers, the browser and the log
        "port_running": "%s：已在連接埠 %d 執行",
        "srv_starting": "正在啟動 %s：%s",
        "srv_failed": "%s 啟動失敗：%s",
        "srv_stopped": "已停止 %s",
        "no_browser": "啟動器的瀏覽器尚未設定 － 請按「設定 Flash 執行環境」。"
                      "只有它會把遊戲自己的伺服器名稱導回這台電腦。",
        "no_plugin": "Flash 執行環境尚未設定 － 請先按「設定 Flash 執行環境」。",
        "opening": "正在開啟 %s",
        "no_chromium": "無法啟動 Chromium：%s",
        "play_real": "正在啟動器的瀏覽器開啟真 Flash 頁面（經本機中繼）",
        "play_ruffle": "Flash 執行環境尚未設定 － 正在啟動器的瀏覽器開啟 Ruffle 播放器，"
                       "它會把遊戲自己的伺服器名稱導到這台電腦"
                       "（按「設定 Flash 執行環境」即可使用真 Flash）",
        "opened": "已開啟 %s",
        "srv_outside": "網上世界的伺服器是在這個視窗以外啟動的 － 請按「停止伺服器」"
                       "再按「啟動伺服器」，好讓它接收新的遊戲檔案。",
        "restarting": "網上世界：正在重新啟動，好讓它提供新的遊戲檔案",
        # the game files: one state per game
        "pkg_client_missing": "套件裡缺少 lpo/fetch_client.py",
        "pkg_cloud_missing": "套件裡缺少 lpo/fetch_cloud.py",
        "check_short": "無法檢查（%s）",
        "not_downloaded": "尚未下載",
        "partial_files": "部分完成（%d／%d 個檔案）",
        "ready": "已就緒",
        "ready_n_files": "已就緒 － 這台電腦上有 %d 個檔案",
        "stale_files": " － 這裡有 CD 版的客戶端檔案（%s）；伺服器啟動時會用官方的檔案取代它們",
        "all_here": "四個遊戲都在這裡",
        "not_here_yet": "還未在這裡：",
        "check_failed": "無法檢查遊戲檔案：%s",
        "gn_LPO": "星願小王子 ONLINE 客戶端",
        "gn_LP1": "LP1 雲端遊戲",
        "gn_LP2": "LP2 雲端遊戲",
        "gn_LP3": "LP3 雲端遊戲",
        # the downloads
        "lpo_nothing": "LPO：沒有需要下載的檔案",
        "lpo_fetching": "LPO：正在從官方伺服器下載 %d 個檔案到 %s",
        "lpo_in_place": "LPO：%d／%d 個檔案已就位（%d 個新的、%d 個失敗、%.0f MB）",
        "failed_rel": "   失敗：%s － %s",
        "cloud_nothing": "%s：沒有需要下載的檔案 － 檔案已齊全",
        "cloud_fetching": "%s：正在從官方伺服器下載 %d 個檔案，約 %.0f MB",
        "cloud_in_place": "%s：%d／%d 個檔案已就位，%d 個無法下載",
        "failed_why": "   失敗：%s（%s）",
        "cloud_left": "%s：仍有 %d 個檔案缺少 － 再執行一次即可繼續",
        "cloud_check_failed": "%s：無法檢查鏡像（%s）",
        "downloading": "正在下載...",
        "dl_running": "已有下載正在進行 － 請先讓它完成",
        "dl_starting": "%s：正在開始...",
        "dl_broken": "%s：下載中斷：%s",
        "dl_progress": "%s：%d／%d 個檔案（%.0f%%）  %s",
        "dl_mb": "%s：%.1f MB",
        "dl_complete": "遊戲檔案已齊全",
        "dl_incomplete": "檔案還未齊全 － 再按一次「下載遊戲檔案」即可繼續",
        # the questions the downloads ask
        "ask_lpo": "要從官方伺服器下載缺少的星願小王子 ONLINE 遊戲檔案嗎？\n\n"
                   "約 %.0f MB，存到\n%s\n\n"
                   "已經存在的檔案會略過，所以會從上次停下的地方繼續。",
        "ask_cd": "要從官方伺服器下載缺少的 %d 個 %s 檔案嗎？\n\n"
                  "約 %.0f MB，只需下載一次，存到\n%s",
        "find_ask": "這個套件裡沒有星願小王子 ONLINE 的遊戲檔案，"
                    "啟動器會找的資料夾裡也都沒有。\n\n"
                    "是  －  立即下載官方檔案（約 %.0f MB，只需一次）\n"
                    "否  －  我已經有遊戲，讓我指出它的資料夾\n"
                    "取消  －  現在不要",
        "find_title": "找出星願小王子 ONLINE 資料夾",
        "no_files_cancel": "LPO：這裡沒有遊戲檔案 － 已取消",
        "no_folder_cancel": "LPO：沒有選擇資料夾 － 已取消",
        "no_swf": "那個資料夾裡沒有 .swf 檔案。\n\n"
                  "請選擇存放 index.swf 與 login.swf 的資料夾。",
        "folder_saved": "遊戲資料夾：%s（已記錄在 lpo/game_dir.txt）",
        "still_checking": "%s：仍在檢查遊戲檔案 － 請稍後再按一次",
        "already_here": "%s：已在這裡（%s）－ 沒有需要下載的東西",
        "dl_cancelled": "%s：已取消下載",
        "online_client": "網上客戶端：%s",
        "picker_sub": "只會下載遊戲缺少的檔案；已經在這裡的遊戲不會被更動。",
        # the window's own hooks
        "word_running": "伺服器運作中",
        "word_stopped": "伺服器已停止",
        "t_online": "網上世界",
        "t_cd": "CD 遊戲",
        "t_relay": "Flash 中繼",
        "t_mp": "多人連線",
        "con_accounts": "帳號網站",
        "con_mods": "模組",
        "t_answers": "有回應",
        "t_no_answer": "沒有回應",
        "t_item": "%s：%d %s",
        "t_sep": " － ",
        "t_ready_n": "%d／%d 個遊戲檔案已就緒",
        "t_prefix": "連線測試：",
        "nothing_to_revert": "macOS 沒有需要還原的東西 － 啟動器從不修改 /etc/hosts",
        "s_online": "網上世界",
        "s_cd": "CD 遊戲",
        "s_relay": "中繼",
        "s_mp": "多人連線",
        "s_flash": "Flash 執行環境",
        "s_files": "遊戲檔案",
        "v_on": "連接埠 %d",
        "v_stopped": "已停止",
        "v_not_set_up": "尚未設定",
        "v_checking": "檢查中...",
        "v_ready_n": "%d／%d 已就緒",
        "footer": "用任何名字登入都可以：這是遊戲的本機鏡像。"
                  "不需要管理員權限 － 這裡不會修改 hosts 檔案。",
        "close_ask": "同時停止本機伺服器嗎？",
        "checking_games": "正在檢查遊戲檔案...",
        "games_note": "遊戲檔案：%s",
        "starting_up": "正在啟動",
        "play_online": "進入網上世界",
        "play_cd": "CD 遊戲 %s",
        "play_cd_row": "玩 CD 遊戲 %s",
        "menu": "選單",
        "sec_servers": "伺服器",
        "server_start": "啟動伺服器",
        "server_stop": "停止伺服器",
        "sec_cd": "CD 遊戲",
        "sec_files": "遊戲檔案",
        "sec_user": "使用者",
        "dn_files": "下載遊戲檔案",
        "check_again": "再檢查一次",
        "setup_flash": "設定 Flash 執行環境",
        "mods": "模組",
        "accounts": "帳號網站",
        "open_client_folder": "開啟星願小王子 ONLINE 資料夾",
        "no_open": "無法開啟 %s（%s）",
        "setup_running": "正在設定 Flash 執行環境...",
        "done": "完成。",
        "setup_failed": "設定失敗：%s",
        # ── the avatar art (see the English table above) ─────────────────────
        "s_avatar": "角色圖片",
        "v_no_pillow": "需要 Pillow",
        "v_art_broken": "無法繪製",
        "install_pillow": "安裝 Pillow",
        "pillow_missing": "角色圖片：%s － 可按選單或左邊按鈕的「安裝 Pillow」直接從這裡安裝。",
        "pillow_running": "角色圖片：正在安裝 Pillow － %s",
        "pillow_ok": "角色圖片：已安裝 Pillow（%s）－ 帳號網站會再次畫出角色"
                     "（已開啟的頁面請重新載入）",
        "pillow_failed": "角色圖片：安裝沒有成功（%s）－ 請自行安裝：%s",
        "pillow_broken": "角色圖片：%s － 這裡無法使用這張圖片需要的角色資料集，"
                         "所以安裝 Pillow 並不能解決",
        "pillow_busy": "已有 Pillow 安裝正在進行 － 請先讓它完成",
        # what is printed before (or without) a window
        "startup_1": "網上世界監聽連接埠 %d（帳號頁面 /web、模組 /mods）",
        "startup_2": "CD 遊戲在連接埠 %d，Flash 中繼在 %d，多人連線中繼在 %d",
        "startup_3": "Flash 執行環境尚未設定 － 按「設定 Flash 執行環境」"
                     "（只需下載一次）即可使用真 Flash",
        "startup_tk": "Tk %s 是系統的舊版本，這個視窗可能一直空白 － "
                      "遊戲運作不變，或改用 --console 執行。",
        "startup_start": "正在啟動伺服器 － 你可以一邊玩，這個視窗一邊開著。",
        "tk_note": "注意：Tk %s 是系統的舊版本。如果視窗空白，\n"
                   "      請執行：  %s macos/launcher_gui.py --console\n"
                   "      或安裝 python.org 的版本，它附帶 Tk 8.6。",
        "con_title": "星願小王子 啟動器（macOS）－ 主控台模式",
        "con_no_tk": "這裡沒有 tkinter，所以沒有視窗。其他一切照樣執行。\n",
        "addresses": "\n位址：",
        "con_open": "\n正在 Flash 瀏覽器開啟網上世界。按 Ctrl-C 停止伺服器。",
        "no_tk_notice": "這裡沒有 tkinter － 改為在這個視窗執行。",
        "no_window_notice": "\n無法建立視窗，所以啟動器改為在這裡執行。",
    },
}

# the action row's keys, in the order actions() offers them: the window builds
# those buttons once, so language_changed() re-words them from the same list
ACTION_KEYS = ("dn_files", "check_again", "setup_flash", "mods", "accounts",
               "install_pillow")


def profile_path():
    """The player record the games read TextLanguage from."""
    return ROOT / 'lpo' / 'profile.json'


def current_language():
    """'en' or 'zh' - read from the same record the badge writes.

    Reading it here (rather than caching it) is what makes the very first render
    right and every hook follow the badge, in both directions.
    """
    try:
        return launcher_ui.read_language(profile_path())
    except Exception:                                              # noqa: BLE001
        return 'en'


def tr(key):
    """The current language's wording for a key."""
    table = TR.get(current_language(), TR['en'])
    return table.get(key, TR['en'].get(key, key))


def game_label(code):
    """The launcher's own name for a game, in the current language.

    Only the row's wording: the titles games() returns are the game's data.
    """
    return tr('gn_%s' % code)


# ── helpers ──────────────────────────────────────────────────────────────────
def port_open(port, host='127.0.0.1'):
    with socket.socket() as s:
        s.settimeout(0.35)
        return s.connect_ex((host, port)) == 0


def python_exe():
    for cand in ('/usr/local/bin/python3', '/opt/homebrew/bin/python3', sys.executable, 'python3'):
        if Path(cand).exists():
            return cand
    return 'python3'


# ── the avatar art: Pillow, the one thing the pack does not carry ────────────
# lpo/avatar.py draws the player's own character and needs Pillow to do it.  The
# pack ships no interpreter (the Windows launcher and this one both run a
# python.org build the user installed), so on a machine without Pillow the
# accounts page shows an empty character and says so.  The check below is the
# pack's OWN render check, run in the interpreter the server is started with, so
# what it answers is exactly what the page will do; the row above the log shows
# it, and installing it is this launcher's job because it is the only thing the
# user has in front of them.
PILLOW_CHECK = r"""
import sys
sys.path.insert(0, sys.argv[1])
print('kind=' + ('venv' if sys.prefix != getattr(sys, 'base_prefix', sys.prefix) else 'system'))
try:
    import PIL
    print('pillow=1')
    print('version=' + str(getattr(PIL, '__version__', '')))
except Exception:
    print('pillow=0')
    print('version=')
try:
    import avatar
    ok = bool(avatar.available())
    print('ok=' + ('1' if ok else '0'))
    print('why=' + ('' if ok else str(avatar.why_not()).replace('\n', ' ')[:200]))
except Exception as exc:
    print('ok=0')
    print('why=' + ('%s: %s' % (type(exc).__name__, exc)).replace('\n', ' ')[:200])
"""
PILLOW_RECHECK = 30.0          # how often the check repeats while Pillow is missing


def pillow_install_cmd(venv=False):
    """The pip command that installs Pillow for the server's own interpreter.

    --user is what a python.org build needs (it cannot write into the framework's
    site-packages without an administrator, and on macOS that is the build the
    pack tells the user to install); a virtualenv refuses --user and does not need
    it, so it is left off there.  The command is the same one the page names.
    """
    cmd = [python_exe(), '-m', 'pip', 'install']
    if not venv:
        cmd.append('--user')
    cmd.append('Pillow')
    return cmd


def server_env(extra=None):
    env = dict(os.environ)
    env['LPO_PORT'] = str(ONLINE_PORT)          # fake_server relays here
    env['PYTHONUNBUFFERED'] = '1'
    if extra:
        env.update(extra)
    return env


def chromium_profile_prefs():
    """Chromium 87 asks before running Flash. Pre-allow it for the local sites so
    the game opens straight away; the user can still change it in the profile."""
    prefs_path = RUNTIME / 'profile' / 'Default' / 'Preferences'
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    prefs = {}
    if prefs_path.exists():
        try:
            prefs = json.loads(prefs_path.read_text('utf-8'))
        except Exception:
            prefs = {}
    allow = {}
    for port in (ONLINE_PORT, CLOUD_PORT):
        allow['http://127.0.0.1:%d,*' % port] = {'setting': 1, 'last_modified': str(int(time.time()))}
        allow['http://localhost:%d,*' % port] = {'setting': 1, 'last_modified': str(int(time.time()))}
    prefs.setdefault('profile', {}).setdefault('content_settings', {}).setdefault('exceptions', {})['flash_plugin'] = allow
    prefs.setdefault('profile', {}).setdefault('default_content_setting_values', {})['plugins'] = 1
    prefs.setdefault('browser', {})['check_default_browser'] = False
    prefs_path.write_text(json.dumps(prefs), 'utf-8')


class Launcher:
    def __init__(self, log):
        self.log = log
        self.procs = {}          # name -> Popen

    # ── servers ─────────────────────────────────────────────────────────────
    def start_servers(self):
        # Order matters: the mirror first, then the CD games' server (which
        # relays to it), then the relay the browser talks to.
        wanted = [
            ('online', [python_exe(), str(ROOT / 'lpo' / 'server.py')], ONLINE_PORT, {}),
            ('cloud', [python_exe(), str(ROOT / 'fake_server.py'), str(CLOUD_PORT), '--no-hosts'],
             CLOUD_PORT, {}),
            ('relay', [python_exe(), str(HERE / 'mac_relay.py')], RELAY_PORT,
             {'LPR_SERVER_PORT': str(CLOUD_PORT), 'LPR_ONLINE_PORT': str(ONLINE_PORT),
              'LPR_RELAY_PORT': str(RELAY_PORT)}),
            ('mprelay', [python_exe(), '-u', str(ROOT / 'lpo' / 'mp_relay.py'),
                         '--port', str(MP_PORT)], MP_PORT, {}),
        ]
        for name, cmd, port, extra_env in wanted:
            if port_open(port):
                self.log(tr('port_running') % (name, port))
                continue
            self.log(tr('srv_starting') % (name, ' '.join(Path(c).name for c in cmd)))
            try:
                proc = subprocess.Popen(cmd, cwd=str(ROOT), env=server_env(extra_env),
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, bufsize=1, start_new_session=True)
            except Exception as exc:
                self.log(tr('srv_failed') % (name, exc))
                continue
            self.procs[name] = proc
            threading.Thread(target=self._pump, args=(name, proc), daemon=True).start()
            time.sleep(0.8)

    def _pump(self, name, proc):
        for line in proc.stdout:
            line = line.rstrip()
            if line and not line.startswith('GET /'):
                self.log('%s| %s' % (name, line))

    def stop_servers(self):
        for name, proc in list(self.procs.items()):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                self.log(tr('srv_stopped') % name)
            except Exception:
                proc.terminate()
            self.procs.pop(name, None)

    def servers_running(self):
        return all(port_open(p) for p in (ONLINE_PORT, CLOUD_PORT, RELAY_PORT, MP_PORT))

    # ── browser ─────────────────────────────────────────────────────────────
    def flash_browser(self, url, extra_args=(), need_plugin=True):
        """Open a page in the launcher's OWN Chromium - the one that carries the proxy.

        --proxy-server=http://127.0.0.1:8900 is not decoration: the games ask for
        ABSOLUTE publisher addresses (www1.little-prince.com.hk, www.starwish-fair.com)
        and the relay is what answers those names from this machine on a Mac, where
        there is no hosts redirect.  A browser started without it reaches the real
        publisher instead - which is why a registered account then "cannot log in".
        Nothing that runs a game may go through the system browser.
        """
        exe = setup_runtime.chromium_binary()
        if not exe:
            self.log(tr('no_browser'))
            return None
        if need_plugin and not setup_runtime.plugin_ready():
            self.log(tr('no_plugin'))
            return None
        chromium_profile_prefs()
        version = setup_runtime.plugin_version() or '32.0.0.465'
        args = [str(exe),
                '--ppapi-flash-path=%s' % PLUGIN_BIN,
                '--ppapi-flash-version=%s' % version,
                '--proxy-server=http://127.0.0.1:%d' % RELAY_PORT,
                '--proxy-bypass-list=127.0.0.1;localhost',
                '--user-data-dir=%s' % (RUNTIME / 'profile'),
                '--no-first-run', '--no-default-browser-check',
                '--disable-features=Translate,MediaRouter',
                '--window-size=1280,800']
        args.extend(extra_args)
        args.append(url)
        self.log(tr('opening') % url)
        # Apple Silicon: Chromium M87 is an Intel binary, so it only runs under
        # Rosetta 2.  macOS reports the missing translation layer as Errno 86
        # "Bad CPU type in executable", which looks like a corrupt download, so
        # check for it first and install Rosetta rather than failing there.
        if setup_runtime.rosetta_needed() and not setup_runtime.install_rosetta(self.log):
            return None
        try:
            return subprocess.Popen(args, cwd=str(ROOT), start_new_session=True)
        except Exception as exc:
            self.log(tr('no_chromium') % exc)
            text = str(exc)
            if ('Bad CPU type' in text or 'Errno 86' in text) \
                    and setup_runtime.install_rosetta(self.log):
                try:
                    return subprocess.Popen(args, cwd=str(ROOT), start_new_session=True)
                except Exception as exc2:
                    self.log(tr('no_chromium') % exc2)
            return None

    def play_online(self):
        """Open the online world in the launcher's own browser - always.

        The game's SWFs call ABSOLUTE publisher addresses, so what matters is not
        only Flash but the relay proxy that flash_browser() puts on Chromium: on
        macOS that proxy is the equivalent of the Windows launcher's hosts file.
        The system browser has no such proxy, so it sends the game's login to the
        real publisher and a registered account "cannot log in" there - which is
        why this never opens the system browser.

        The Flash runtime (bundled Chromium M87 + its Pepper Flash plugin) is what
        plays the real thing.  When it is not ready, /play opens instead: the same
        game through the install-free Ruffle player, which Chromium M87 runs with no
        plugin at all - still through the proxy.
        """
        runtime_ready = bool(setup_runtime.chromium_binary()
                             and setup_runtime.plugin_ready())
        if runtime_ready:
            self.log(tr('play_real'))
            return self.flash_browser('http://127.0.0.1:%d/LP/Po/flash' % ONLINE_PORT)
        self.log(tr('play_ruffle'))
        return self.flash_browser('http://127.0.0.1:%d/play' % ONLINE_PORT,
                                  need_plugin=False)

    def play_cd(self, which):
        return self.flash_browser('http://127.0.0.1:%d/%s/index.html' % (CLOUD_PORT, which))

    def open_url(self, url):
        subprocess.Popen(['open', url])
        self.log(tr('opened') % url)

    def open_mods(self):
        """The mods panel.

        On Windows the entry sits in the publisher's browser menu bar; macOS has no
        Electron shell of its own (the games run in the bundled Flash runtime), so
        the launcher is where the entry belongs.  The panel itself is the same page
        on the local server, and the same saved values either way.
        """
        return self.open_url('http://127.0.0.1:%d/mods' % ONLINE_PORT)

    def restart_online(self):
        """Make the online server pick up client files that just arrived.

        lpo/server.py decides where the game files are when it starts, so a
        server that was already running keeps serving the folder it chose.
        """
        if not port_open(ONLINE_PORT):
            return
        proc = self.procs.get('online')
        if proc is None:
            self.log(tr('srv_outside'))
            return
        self.procs.pop('online', None)
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            proc.terminate()
        for _ in range(24):
            if not port_open(ONLINE_PORT):
                break
            time.sleep(0.25)
        self.log(tr('restarting'))
        self.start_servers()


# ── the game files ───────────────────────────────────────────────────────────
# The same job the Windows launcher's file checks do: say which of the four games
# are on this machine and fetch the rest from the publisher.  The checks and the
# fetches live in lpo/fetch_client.py and lpo/fetch_cloud.py, loaded by path
# because they are command-line tools rather than an installed package - exactly
# how Start_Server_GUI.pyw loads them.
#
# One status row per game, never one verdict for the group: the three cloud games
# are a single product but each is its own download, and a machine with LP1 alone
# must not be told the others are "ready".
GAME_ROWS = (('file_LPO', 'LPO', 'Little Prince Online client'),
             ('file_LP1', 'LP1', 'LP1 cloud game'),
             ('file_LP2', 'LP2', 'LP2 cloud game'),
             ('file_LP3', 'LP3', 'LP3 cloud game'))
GAMES = tuple((code, name) for _key, code, name in GAME_ROWS)
GAME_NAMES = dict(GAMES)
_MODS = {}


def fetcher(name, rel):
    """lpo/fetch_client.py or lpo/fetch_cloud.py, loaded once.

    None when the package does not carry the tool, so every caller has to say
    what it could not check instead of guessing.
    """
    if name in _MODS:
        return _MODS[name]
    mod = None
    path = ROOT / rel
    if path.exists():
        try:
            spec = importlib.util.spec_from_file_location(name, str(path))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as exc:                                   # noqa: BLE001
            print('could not load %s: %s' % (path, exc), file=sys.stderr)
            mod = None
    _MODS[name] = mod
    return mod


def server_module():
    """lpo/server.py itself, so the window and the game server can never disagree
    about where the client is.

    `_resolve_game_dir()` there is the one authority for the search order
    ($LPO_GAME_DIR, lpo/game, lpo/game_dir.txt, ...); importing it beats copying
    it, because two copies of a search order drift.
    """
    if 'server' not in _MODS:
        mod = None
        try:
            if str(ROOT / 'lpo') not in sys.path:
                sys.path.insert(0, str(ROOT / 'lpo'))
            # it logs a line while it is imported; that is not ours to print
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                import server as mod                                # noqa: F401
        except Exception as exc:                                   # noqa: BLE001
            print('could not load lpo/server.py: %s' % exc, file=sys.stderr)
            mod = None
        _MODS['server'] = mod
    return _MODS['server']


def has_swfs(path):
    """A candidate counts only when it really holds game files (server.py's rule)."""
    try:
        return Path(path).is_dir() and next(Path(path).glob('*.swf'), None) is not None
    except Exception:                                              # noqa: BLE001
        return False


def _resolve_game_dir_here():
    """server.py's order, mirrored - used only if that module will not load."""
    here = ROOT / 'lpo'
    env = os.environ.get('LPO_GAME_DIR')
    if env and has_swfs(env):
        return Path(env)
    for cand in (here / 'game', ROOT / 'game'):
        if has_swfs(cand):
            return cand
    try:
        txt = here / 'game_dir.txt'
        if txt.is_file():
            p = Path(txt.read_text(encoding='utf-8').strip().strip('"'))
            if has_swfs(p):
                return p
    except Exception:                                              # noqa: BLE001
        pass
    for cand in (Path.home() / 'littleprince-online',
                 Path.home() / 'Downloads' / 'Little Prince Online'):
        if has_swfs(cand):
            return cand
    return here


def client_dir():
    """Where the online client is, in the server's own search order."""
    mod = server_module()
    if mod is not None:
        try:
            return Path(mod.GAME_DIR)
        except Exception:                                          # noqa: BLE001
            pass
    return _resolve_game_dir_here()


def save_game_dir(path):
    """Remember the client's folder in lpo/game_dir.txt - the file lpo/server.py
    reads at its next start, which is what makes the two agree afterwards."""
    mod = server_module()
    if mod is not None:
        try:
            return Path(mod.save_game_dir(path))
        except Exception:                                          # noqa: BLE001
            pass
    (ROOT / 'lpo' / 'game_dir.txt').write_text(str(Path(path)) + '\n', encoding='utf-8')
    return Path(path)


def client_download_dir():
    """Where a newly downloaded client goes: over a part-finished copy in place,
    otherwise into lpo/game - the second place the server looks, so a download
    needs no further setup to be found."""
    cur = client_dir()
    if has_swfs(cur):
        return cur
    return ROOT / 'lpo' / 'game'


def cloud_dir():
    """The mirrored cloud games.  $LPR_CLOUD_DIR points the window at a mirror
    somewhere else - the same idea as fetch_cloud.py's own --cloud."""
    return Path(os.environ.get('LPR_CLOUD_DIR') or (ROOT / 'cloud'))


def _game(code, state, text, present=0, total=0, detail='', left=0, **extra):
    """One status row's worth of answer."""
    row = {'code': code, 'name': game_label(code), 'state': state, 'text': text,
           'present': present, 'total': total, 'detail': detail, 'bytes_left': left,
           'ready': state == 'ready'}
    row.update(extra)
    return row


def client_state():
    """The Little Prince Online client: what is here, what is missing."""
    dest = client_dir()
    mod = fetcher('lpo_fetch', 'lpo/fetch_client.py')
    if mod is None:
        return _game('LPO', 'unknown', tr('pkg_client_missing'),
                     detail=str(dest))
    try:
        res = mod.check(dest)
        sizes = dict(mod.read_manifest())
    except Exception as exc:                                       # noqa: BLE001
        return _game('LPO', 'unknown', tr('check_short') % str(exc)[:40],
                     detail=str(dest))
    total, present = res['total'], res['present']
    absent = res['missing'] + res['wrong']
    # index.swf and login.swf are what the game opens with; a folder holding
    # neither is not a client, however many other .swf files are in it.
    movies = [n for n in ('index.swf', 'login.swf') if not (dest / n).is_file()]
    left = sum(sizes.get(r, 0) for r in absent)
    extra = {'found': has_swfs(dest), 'dir': str(dest)}
    if not absent and not movies:
        return _game('LPO', 'ready', tr('ready'), present, total, str(dest), 0, **extra)
    if not present:
        return _game('LPO', 'missing', tr('not_downloaded'), present, total, str(dest),
                     left, **extra)
    return _game('LPO', 'partial',
                 tr('partial_files') % (present, total),
                 present, total, str(dest), left, **extra)


def cloud_state(code, cloud, mod, manifest, checked):
    """One mirrored cloud game, against the mirror's own manifest."""
    folder = cloud / code
    rows = [r for r, _s in manifest if r.startswith(code + '/')]
    total = len(rows)
    sizes = dict(manifest)
    if not folder.is_dir():
        return _game(code, 'missing', tr('not_downloaded'), 0, total, str(folder),
                     sum(sizes.get(r, 0) for r in rows))
    try:
        missing, wrong = checked if checked is not None else mod.check(cloud)
        bad = [r for r in missing + wrong if r.startswith(code + '/')]
        try:
            stale = mod.client_bad(cloud, code)     # the CD's registration shell
        except Exception:                                          # noqa: BLE001
            stale = []
    except Exception as exc:                                       # noqa: BLE001
        return _game(code, 'unknown', tr('check_short') % str(exc)[:40],
                     detail=str(folder))
    present = max(0, total - len(bad) - len(stale))
    if total and not bad and not stale:
        return _game(code, 'ready', tr('ready'), total, total, str(folder), 0)
    left = sum(sizes.get(r, 0) for r in bad)
    detail = str(folder)
    if stale and not bad:
        detail += tr('stale_files') % ', '.join(stale)
    if not present:
        return _game(code, 'missing', tr('not_downloaded'), present, total, detail, left)
    return _game(code, 'partial', tr('partial_files') % (present, total),
                 present, total, detail, left)


def scan_games():
    """What is here, for all four games.  Blocking - call it on a worker thread."""
    cloud = cloud_dir()
    mod = fetcher('lpo_cloud', 'lpo/fetch_cloud.py')
    manifest, checked = [], None
    if mod is not None:
        try:
            manifest = mod.read_manifest(cloud)
            checked = mod.check(cloud)          # one pass of the mirror serves all three
        except Exception:                                          # noqa: BLE001
            manifest, checked = [], None
    out = {'LPO': client_state()}
    for code, _name in GAMES:
        if code == 'LPO':
            continue
        if mod is None:
            folder = cloud / code
            try:
                swfs = len([f for f in os.listdir(folder) if f.lower().endswith('.swf')])
            except OSError:
                swfs = 0
            out[code] = _game(code, 'ready' if swfs else 'missing',
                              tr('ready_n_files') % swfs if swfs
                              else tr('not_downloaded'), detail=str(folder))
            continue
        out[code] = cloud_state(code, cloud, mod, manifest, checked)
    return out


_STATE = {'at': 0.0, 'busy': False, 'games': {}, 'note': ''}


def check_games(force=False):
    """The last answer - never a fresh scan on the caller's thread.

    The cloud check stats every file in the mirror (29,503 of them), so running
    it from a refresh loop is exactly what once made the Windows launcher stop
    responding.  This hands back the last result and, when it is older than ~15 s
    (or `force` is set), starts a scan on a worker thread.
    """
    if (force or not _STATE['games'] or time.time() - _STATE['at'] > 15) \
            and not _STATE['busy']:
        _STATE['busy'] = True

        def work():
            try:
                games = scan_games()
                away = [g['name'] for g in games.values() if not g['ready']]
                note = (tr('all_here') if not away
                        else tr('not_here_yet') + ', '.join(away))
                _STATE.update({'games': games, 'note': note, 'at': time.time()})
            except Exception as exc:                               # noqa: BLE001
                _STATE.update({'note': tr('check_failed') % str(exc)[:60],
                               'at': time.time()})
            finally:
                _STATE['busy'] = False

        threading.Thread(target=work, daemon=True).start()
    return _STATE


def download_game(code, log=print, progress=None, only=None):
    """Fetch one of the four games.  Blocking - the window runs it on a thread.

    `only` narrows the work to the manifest entries whose path contains that
    text, which is how the wiring is exercised without pulling 912 MB.
    Returns True when the game verifies complete afterwards.
    """
    if code == 'LPO':
        return _download_client(log, progress, only)
    return _download_cloud(code, log, progress, only)


def _download_client(log, progress, only):
    mod = fetcher('lpo_fetch', 'lpo/fetch_client.py')
    if mod is None:
        log(tr('pkg_client_missing'))
        return False
    dest = client_download_dir()
    rows = mod.read_manifest()
    if only:
        rows = [r for r in rows if only in r[0]]
    if not rows:
        log(tr('lpo_nothing'))
        return False
    log(tr('lpo_fetching') % (len(rows), dest))

    def say(st):
        if progress is None:
            return
        total_bytes = st.get('total_bytes') or 0
        progress({'files': st.get('files', 0), 'total': st.get('total', 0),
                  'bytes': st.get('bytes', 0), 'total_bytes': total_bytes,
                  'current': st.get('current', ''),
                  'percent': (100.0 * st.get('bytes', 0) / total_bytes) if total_bytes else 0})

    st = mod.fetch(dest=dest, workers=6, progress=say, only=only,
                   log=lambda m: log(str(m).strip()))
    done = st['ok'] + st['skipped']
    log(tr('lpo_in_place')
        % (done, st['total'], st['ok'], len(st['failed']), st['bytes'] / 1e6))
    for rel, err in st['failed'][:5]:
        log(tr('failed_rel') % (rel, err))
    return bool(st['total']) and not st['failed'] and done == st['total']


def _download_cloud(code, log, progress, only):
    mod = fetcher('lpo_cloud', 'lpo/fetch_cloud.py')
    if mod is None:
        log(tr('pkg_cloud_missing'))
        return False
    cloud = cloud_dir()
    try:
        missing, wrong = mod.check(cloud)
    except Exception as exc:                                       # noqa: BLE001
        log(tr('cloud_check_failed') % (code, exc))
        return False
    wanted = set(r for r in missing + wrong if r.startswith(code + '/'))
    if only:
        wanted = set(r for r in wanted if only in r)
    if not wanted:
        log(tr('cloud_nothing') % code)
        return True
    sizes = dict(mod.read_manifest(cloud))
    log(tr('cloud_fetching')
        % (code, len(wanted), sum(sizes.get(r, 0) for r in wanted) / 1e6))
    seen = {'n': 0}

    def say(text):
        text = str(text).strip()
        if text.startswith('fetched'):              # one line per file, from the fetcher
            seen['n'] += 1
            parts = text.split()
            if progress is not None:
                progress({'files': seen['n'], 'total': len(wanted), 'bytes': 0,
                          'total_bytes': 0, 'current': parts[1] if len(parts) > 1 else '',
                          'percent': 100.0 * seen['n'] / len(wanted)})
        log(text)

    ok, failed = mod.fetch(cloud, only=wanted, log=say)
    log(tr('cloud_in_place') % (code, ok, len(wanted), len(failed)))
    for rel, why in failed[:5]:
        log(tr('failed_why') % (rel, why))
    try:
        left_missing, left_wrong = mod.check(cloud)
        left = [r for r in left_missing + left_wrong if r.startswith(code + '/')]
    except Exception:                                              # noqa: BLE001
        left = list(failed)
    if left:
        log(tr('cloud_left') % (code, len(left)))
        return False
    return True


# ── console mode (no tkinter) ────────────────────────────────────────────────
def console_main():
    print(tr('con_title'))
    print(tr('con_no_tk'))
    launcher = Launcher(lambda m: print('  ' + m, flush=True))
    setup_runtime.report()
    print()
    launcher.start_servers()
    for _ in range(40):
        if launcher.servers_running():
            break
        time.sleep(0.5)
    print(tr('addresses'))
    print('  %-13s http://127.0.0.1:%d/LP/Po/flash' % (tr('t_online'), ONLINE_PORT))
    print('  %-13s http://127.0.0.1:%d/index.html' % (tr('t_cd'), CLOUD_PORT))
    print('  %-13s http://127.0.0.1:%d/web' % (tr('con_accounts'), ONLINE_PORT))
    print('  %-13s http://127.0.0.1:%d/mods' % (tr('con_mods'), ONLINE_PORT))
    print(tr('con_open'))
    launcher.play_online()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        launcher.stop_servers()
    return 0


# ── window mode ──────────────────────────────────────────────────────────────
def tk_report():
    """Python + Tk versions, on stderr, before the window is drawn.

    Apple's Tk 8.5 (the one that prints "The system version of Tk is deprecated")
    draws an empty window on current macOS: the frame appears but ttk/plain widgets
    never paint.  Recording the versions here means a blank window still says which
    Tk it was, instead of failing silently.
    """
    import tkinter
    py = '%d.%d.%d' % sys.version_info[:3]
    tk_ver = tkinter.TkVersion
    print('python %s (%s)' % (py, sys.executable), file=sys.stderr)
    print('tk %s' % tk_ver, file=sys.stderr)
    if tk_ver < 8.6:
        print(tr('tk_note') % (tk_ver, sys.executable),
              file=sys.stderr)
    return tk_ver


# ── window mode ──────────────────────────────────────────────────────────────
# The window itself is launcher_ui.py at the root of the pack - the same one the
# Windows launcher (Start_Server_GUI.pyw) draws.  What is left here is the macOS
# side of it: the four servers as subprocesses, the bundled Pepper Flash runtime,
# and the game files.

def readiness_colour(info):
    """Green for a game that is here, amber for one part-way, red for absent."""
    if not info:
        return launcher_ui.DIM
    if info['ready']:
        return launcher_ui.GREEN
    return launcher_ui.AMBER if info['state'] == 'partial' else launcher_ui.RED


class MacBackend:
    """The macOS side of the launcher.

    No hosts file and no administrator rights (the browser is pointed at the local
    relay instead), the servers are subprocesses rather than threads, and the game
    plays in the bundled Chromium + Pepper Flash runtime instead of the publisher's
    Windows browser.
    """

    name = 'Little Prince Launcher (macOS)'
    title = 'Little Prince Launcher'
    version = '1.1'
    background_start = True          # the servers are subprocesses: keep the window live
    mono_font = ('Menlo', 9)

    def __init__(self, tk_ver=None):
        self.tk_ver = tk_ver
        self.launcher = None
        self.ui = None
        self._sink = lambda m: print('  ' + str(m), flush=True)
        self._last_line = ''
        self._progress = ''
        self._note = ''
        self._games = {}
        self._ports = {}
        self._ports_at = 0.0
        self._ports_busy = False
        self._dl = {'code': '', 'done': False, 'ok': False, 'at': 0.0}
        self._prog = {}
        self._picker = None
        # the language the badge has selected: tr() reads it live from the player
        # record, and this is what language_changed() last saw
        self._lang = current_language()
        # the avatar art's one dependency: what the pack's own render check said,
        # and how far installing Pillow has got (both run on workers)
        self._pil = {'state': 'unknown', 'why': '', 'version': '', 'venv': False,
                     'at': 0.0, 'busy': False, 'installing': False, 'logged': None}

    # ── the log ─────────────────────────────────────────────────────────────
    def log(self, message):
        text = str(message).rstrip()
        if text:
            self._last_line = text[:110]
        self._sink(text)

    def attach_log(self, sink):
        self._sink = sink
        self.launcher = Launcher(self.log)

    # ── identity ────────────────────────────────────────────────────────────
    def assets_dir(self):
        return str(ROOT)

    @property
    def url(self):
        return 'http://127.0.0.1:%d' % ONLINE_PORT

    def error_log_path(self):
        return str(HERE / 'launcher-error.log')

    def profile_path(self):
        """The player record the games read TextLanguage from (the ZH badge writes it).

        The same file the Windows launcher writes, in the same place in the pack.
        """
        return profile_path()

    def language_changed(self, lang):
        """The badge switched the language - the profile is already written.

        The marquee, the stats, the footer, the drawer, the banner's button and
        the log all come from hooks the window re-reads on its next refresh, so
        they follow by themselves.  The action row is the exception: the window
        builds those buttons once, so they are re-worded here (and the dict they
        are filed in re-keyed, or _set_busy() would not find them again).
        """
        self._lang = 'zh' if str(lang).strip().lower().startswith('zh') else 'en'
        buttons = getattr(self.ui, 'action_buttons', None)
        if not buttons:
            return
        if self._dl['code'] and not self._dl['done']:
            return                      # a running download owns that button's word
        for key in ACTION_KEYS:
            new = tr(key)
            for old in (TR['en'].get(key), TR['zh'].get(key)):
                if old and old in buttons:
                    if old != new:
                        self.ui.set_action_text(old, new)
                        buttons[new] = buttons.pop(old)
                    break

    def startup_lines(self):
        lines = [tr('startup_1') % ONLINE_PORT,
                 tr('startup_2') % (CLOUD_PORT, RELAY_PORT, MP_PORT)]
        if not setup_runtime.chromium_binary() or not setup_runtime.plugin_ready():
            lines.append(tr('startup_3'))
        if self.tk_ver is not None and self.tk_ver < 8.6:
            lines.append(tr('startup_tk') % self.tk_ver)
        lines.append(tr('startup_start'))
        return lines

    def autostart(self):
        return True

    # ── the servers ─────────────────────────────────────────────────────────
    def _probe_ports(self):
        """Port state, on a worker: a dead port costs 0.35 s to find out."""
        now = time.time()
        if now - self._ports_at > 2.0 and not self._ports_busy:
            self._ports_busy = True

            def work():
                try:
                    self._ports = dict((p, port_open(p))
                                       for p in (ONLINE_PORT, CLOUD_PORT, RELAY_PORT,
                                                 MP_PORT))
                    self._ports_at = time.time()
                finally:
                    self._ports_busy = False

            threading.Thread(target=work, daemon=True).start()
        return self._ports

    def servers_up(self):
        ports = self._probe_ports()
        if not ports:
            return all(port_open(p) for p in (ONLINE_PORT, CLOUD_PORT, RELAY_PORT))
        return all(ports.get(p) for p in (ONLINE_PORT, CLOUD_PORT, RELAY_PORT))

    def running(self):
        return self.servers_up()

    def status(self):
        if self.servers_up():
            return tr('word_running'), True
        return tr('word_stopped'), False

    def start(self):
        if self.launcher is None:
            self.launcher = Launcher(self.log)
        self.launcher.start_servers()
        self._ports_at = 0.0            # the next tick probes them again
        self._probe_ports()

    def stop(self):
        if self.launcher is not None:
            self.launcher.stop_servers()
        self._ports_at = 0.0

    def test(self):
        """What 'Test the connection' logs: every port and every game's files."""
        parts = []
        for name, port in ((tr('t_online'), ONLINE_PORT), (tr('t_cd'), CLOUD_PORT),
                           (tr('t_relay'), RELAY_PORT), (tr('t_mp'), MP_PORT)):
            parts.append(tr('t_item') % (name, port,
                                         tr('t_answers') if port_open(port)
                                         else tr('t_no_answer')))
        here = sum(1 for g in self._games.values() if g['ready'])
        parts.append(tr('t_ready_n') % (here, len(GAMES)))
        return tr('t_prefix') + tr('t_sep').join(parts)

    def revert_hosts(self):
        """macOS has no hosts redirect to revert.  The entry is not offered."""
        self.log(tr('nothing_to_revert'))
        return False

    def stats(self):
        ports = self._probe_ports()

        def state(port):
            if not ports:
                return '...'
            return tr('v_on') % port if ports.get(port) else tr('v_stopped')

        ready = sum(1 for g in self._games.values() if g['ready'])
        flash = tr('ready') if (setup_runtime.chromium_binary()
                                and setup_runtime.plugin_ready()) else tr('v_not_set_up')
        return [(tr('s_online'), state(ONLINE_PORT)),
                (tr('s_cd'), state(CLOUD_PORT)),
                (tr('s_relay'), state(RELAY_PORT)),
                (tr('s_mp'), state(MP_PORT)),
                (tr('s_flash'), flash),
                (tr('s_files'), tr('v_ready_n') % (ready, len(GAMES)) if self._games
                 else tr('v_checking')),
                # the accounts page's own dependency: the row says whether the
                # player's character can be drawn, and follows the check by itself
                (tr('s_avatar'), self.avatar_text())]

    def footer(self):
        return tr('footer')

    def close(self):
        from tkinter import messagebox
        if self.launcher is not None and self.launcher.procs:
            if not messagebox.askyesno(self.title, tr('close_ask')):
                return False
            self.launcher.stop_servers()
        return True

    # ── the game files ──────────────────────────────────────────────────────
    def check_again(self):
        self.log(tr('checking_games'))
        check_games(force=True)

    # ── the avatar art: the check, the row, and the one-click install ────────
    def _probe_pillow(self, force=False):
        """Ask the pack's own render check, in the python the server runs on.

        One short-lived interpreter, on a worker: the answer is what the row shows
        and the window must never wait for it.  It is looked at again while the
        answer is no (the user may install Pillow in a terminal), and always right
        after this launcher installs it.
        """
        pil = self._pil
        if pil['busy']:
            return pil
        if not force:
            if pil['state'] == 'ok':
                return pil                          # a yes cannot go stale here
            if time.time() - pil['at'] < PILLOW_RECHECK:
                return pil
        pil['busy'] = True

        def work():
            try:
                out = subprocess.run([python_exe(), '-c', PILLOW_CHECK, str(ROOT / 'lpo')],
                                     cwd=str(ROOT), env=server_env(), text=True,
                                     capture_output=True, timeout=180)
                lines = {}
                for line in (out.stdout or '').splitlines():
                    key, _sep, value = line.partition('=')
                    lines[key.strip()] = value.strip()
                if lines.get('ok') == '1':
                    state = 'ok'
                elif lines.get('pillow') == '1':
                    state = 'broken'            # Pillow is here: the dataset is the trouble
                else:
                    state = 'no_pillow'
                why = lines.get('why') or ''
                if 'ok' not in lines:           # the check itself could not run
                    why = ((out.stderr or '').strip().splitlines() or ['no answer'])[-1]
                pil.update({'state': state, 'why': why[:200],
                            'version': lines.get('version') or '',
                            'venv': lines.get('kind') == 'venv',
                            'at': time.time()})
            except Exception as exc:                                    # noqa: BLE001
                pil.update({'state': 'unknown', 'at': time.time(),
                            'why': '%s: %s' % (type(exc).__name__, exc)})
            finally:
                pil['busy'] = False

        threading.Thread(target=work, daemon=True).start()
        return pil

    def pillow_cmd_text(self):
        """The pip command this launcher would run, as the log and the page name it."""
        return ' '.join(pillow_install_cmd(venv=self._pil['venv']))

    def avatar_text(self):
        """What the avatar-art row says."""
        state = self._pil['state']
        if state == 'ok':
            return tr('ready')
        if state == 'no_pillow':
            return tr('v_no_pillow')
        if state == 'broken':
            return tr('v_art_broken')
        return tr('v_checking')

    def _say_pillow(self):
        """Log the state once, and again only when it changes - the row follows it.

        Called on every tick, so the row (and the button) follow the answer by
        themselves the moment Pillow is installed: by this launcher, or by hand in
        another window.
        """
        pil = self._pil
        if pil['busy'] or pil['state'] == 'unknown':
            return
        seen = (pil['state'], pil['version'] if pil['state'] == 'ok' else pil['why'][:60])
        if seen == pil['logged']:
            return
        pil['logged'] = seen
        if pil['state'] == 'ok':
            self.log(tr('pillow_ok') % (pil['version'] or 'ok'))
        elif pil['state'] == 'no_pillow':
            self.log(tr('pillow_missing') % pil['why'])
        else:
            self.log(tr('pillow_broken') % pil['why'])
        self._paint_pillow_button(pil['state'] == 'ok')

    def _paint_pillow_button(self, ok):
        """The row's Install Pillow button only stands out while it is needed."""
        _label, btn = self._action_button('install_pillow')
        if btn is None:
            return
        try:
            if ok:
                btn.configure(bg='#1d1d24', fg=launcher_ui.DIM,
                              activebackground=launcher_ui.GOLD_DIM,
                              activeforeground=launcher_ui.GOLD)
            else:
                btn.configure(bg=launcher_ui.GOLD, fg='#1a1a1a',
                              activebackground='#f2dcae', activeforeground='#1a1a1a')
        except Exception:                                           # noqa: BLE001
            pass

    def install_pillow_task(self):
        """Install Pillow for the interpreter the server runs on - on a worker.

        pip's own output goes into this window's log as it arrives (the window must
        never freeze for it), and when it finishes the render check is run again, so
        the row answers without a restart: the server picks the new Pillow up by
        itself and the accounts page draws the character on its next reload.
        """
        if self._pil['installing']:
            self.log(tr('pillow_busy'))
            return
        cmd = pillow_install_cmd(venv=self._pil['venv'])
        self._pil['installing'] = True
        self._progress = tr('pillow_running') % ' '.join(cmd)

        def worker():
            last, rc = '', -1
            try:
                self.log(tr('pillow_running') % ' '.join(cmd))
                proc = subprocess.Popen(cmd, cwd=str(ROOT), env=server_env(),
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in proc.stdout:            # pip's progress, as it happens
                    line = str(line).rstrip()
                    if line:
                        last = line
                        self.log('   pip: ' + line)
                rc = proc.wait()
            except Exception as exc:                                    # noqa: BLE001
                last = '%s: %s' % (type(exc).__name__, exc)
            self._pil['installing'] = False
            self._progress = ''
            if rc != 0:
                self.log(tr('pillow_failed') % ((last or 'pip exit %d' % rc)[:100],
                                                ' '.join(cmd)))
            self._probe_pillow(force=True)          # the row flips on its own

        threading.Thread(target=worker, daemon=True).start()

    def tick(self):
        state = check_games()
        games = state['games']
        if games:
            self._games = games
        if state['note'] and state['note'] != self._note:
            self._note = state['note']       # say it once, not every 0.5 s
            self.log(tr('games_note') % state['note'])
        self._probe_pillow()
        self._say_pillow()
        self._probe_ports()
        self._tick_download()

    def status_line(self):
        if self._progress:
            return self._progress
        if self._last_line:
            return self._last_line
        return tr('starting_up')

    # ── the banner ──────────────────────────────────────────────────────────
    def games(self):
        """The four games, named as the Windows launcher names them."""
        return [('LP1', '星願小王子', '當幸福遇見勇氣'),
                ('LP2', '星願外傳', '星座消失之謎'),
                ('LP3', '星願歷奇', '農場大作戰'),
                ('LPO', '星願小王子 ONLINE', '網上學習新體驗')]

    def default_game(self):
        return 'LPO'                    # the online world is what this launcher is for

    def play_label(self, code):
        return tr('play_online') if code == 'LPO' else tr('play_cd') % code

    def play(self, code):
        """The banner's button speaks for the tab that is showing.

        LPO is the online world (real Flash when the runtime is ready, the Ruffle
        player when it is not); LP1/LP2/LP3 are the three CD games served by
        fake_server, which the bundled Flash runtime opens with real Flash.
        """
        if code == 'LPO':
            return self.play_online()
        return self.play_cd(code)

    def play_online(self):
        return self.launcher.play_online()

    def play_cd(self, which):
        return self.launcher.play_cd(which)

    # ── the drawer ──────────────────────────────────────────────────────────
    def menu_title(self):
        return tr('menu')

    def menu(self):
        ui = self.ui
        live = self.servers_up()
        return [
            (None, [(tr('play_online'), self.play_online, True)]),
            (tr('sec_servers'), [
                (tr('server_start'), ui.start_clicked, not live),
                (tr('server_stop'), ui.stop_clicked, live),
                (tr('setup_flash'), self.setup_runtime_task, True),
                (tr('install_pillow'), self.install_pillow_task, True),
            ]),
            (tr('sec_cd'), [
                (tr('play_cd_row') % 'LP1', lambda: self.play_cd('LP1'), True),
                (tr('play_cd_row') % 'LP2', lambda: self.play_cd('LP2'), True),
                (tr('play_cd_row') % 'LP3', lambda: self.play_cd('LP3'), True),
            ]),
            (tr('sec_files'), [
                (tr('dn_files'), self.open_picker, True),
                (tr('check_again'), self.check_again, True),
            ]),
            (tr('sec_user'), [
                (tr('accounts'), self.open_accounts, True),
                (tr('mods'), self.open_mods, True),
                (tr('open_client_folder'), self.open_client_folder, True),
            ]),
        ]

    def open_accounts(self):
        """The accounts page - /web on the local server, what the badge opens."""
        return self.launcher.open_url('http://127.0.0.1:%d/web' % ONLINE_PORT)

    def open_mods(self):
        """The mods panel: the same page on the local server as on Windows.

        On Windows the entry sits in the publisher's browser menu bar; macOS has no
        Electron shell of its own (the games run in the bundled Flash runtime), so
        the launcher is where the entry belongs.
        """
        return self.launcher.open_mods()

    def open_client_folder(self):
        """Reveal the folder the online client is served from."""
        path = client_dir()
        try:
            subprocess.Popen(['open', str(path)])
            self.log(tr('opened') % path)
        except Exception as exc:                                       # noqa: BLE001
            self.log(tr('no_open') % (path, exc))

    def setup_runtime_task(self):
        """Fetch and unpack the Flash runtime - one download, on a worker."""

        def work():
            try:
                self.log(tr('setup_running'))
                setup_runtime.install_chromium(log=self.log)
                self.log(tr('done'))
            except Exception as exc:                                    # noqa: BLE001
                self.log(tr('setup_failed') % exc)

        threading.Thread(target=work, daemon=True).start()

    # ── the game files: the count, and the downloads ────────────────────────
    def actions(self):
        return [(tr('dn_files'), self.open_picker, True),
                (tr('check_again'), self.check_again, False),
                (tr('setup_flash'), self.setup_runtime_task, False),
                (tr('mods'), self.open_mods, False),
                (tr('accounts'), self.open_accounts, False),
                # the avatar art's one dependency: gold while it is missing (the
                # check repaints it), plain once the character can be drawn
                (tr('install_pillow'), self.install_pillow_task, False)]

    def actions_summary(self):
        """The right-hand side of the row: what is here, and what a fetch is doing.

        One line, but it keeps the Windows launcher's wording - and the game-file
        count that the old Status panel used to spell out row by row.
        """
        if self._progress:
            return self._progress
        if not self._games:
            return tr('checking_games')
        ready = sum(1 for g in self._games.values() if g['ready'])
        text = tr('t_ready_n') % (ready, len(GAMES))
        behind = ['%s %s' % (code, self._games[code]['text'])
                  for code, _name in GAMES
                  if code in self._games and not self._games[code]['ready']]
        if behind:
            text += '  -  ' + ' · '.join(behind)
        return text[:120]

    def _action_button(self, key):
        """The action row's button for a key, under either language's wording.

        The window builds that row once and files each button under the label it
        was created with, so this looks for both spellings (language_changed()
        re-keys the dict, but a lookup must not depend on it having run).
        """
        buttons = getattr(self.ui, 'action_buttons', None) or {}
        for label in (tr(key), TR['en'].get(key), TR['zh'].get(key)):
            if label and label in buttons:
                return label, buttons[label]
        return None, None

    def _set_busy(self, on):
        """The download button goes quiet while its own work runs."""
        ui = self.ui
        label, btn = self._action_button('dn_files')
        if btn is None:
            return
        ui.set_action_text(label, tr('downloading') if on else tr('dn_files'))
        launcher_ui.set_button_state(btn, not on)
        try:
            btn.configure(bg='#2a2a33' if on else launcher_ui.GOLD,
                          fg=launcher_ui.DIM if on else '#101014')
        except Exception:                                              # noqa: BLE001
            pass

    def run_download(self, code, only=None):
        """Fetch one game on a worker thread.  True when it started."""
        if self._dl['code'] and not self._dl['done']:
            self.log(tr('dl_running'))
            return False
        self._prog = {}
        self._dl = {'code': code, 'done': False, 'ok': False, 'at': 0.0}
        self._set_busy(True)
        self._progress = tr('dl_starting') % code

        def worker():
            ok = False
            try:
                ok = download_game(code, log=self.log, only=only,
                                   progress=lambda st: self._prog.update(st))
            except BaseException as exc:                               # noqa: BLE001
                self.log(tr('dl_broken') % (code, exc))
            self._dl.update({'code': code, 'done': True, 'ok': bool(ok),
                             'at': time.time()})
            if code == 'LPO' and ok:
                self.launcher.restart_online()   # it reads the folder when it starts

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _show_progress(self):
        prog = self._prog
        if not prog:
            return
        total = prog.get('total') or 0
        if total:
            self._progress = (tr('dl_progress')
                              % (self._dl['code'], prog.get('files', 0), total,
                                 prog.get('percent', 0),
                                 (prog.get('current') or '')[:30]))
        else:
            self._progress = tr('dl_mb') % (self._dl['code'],
                                            prog.get('bytes', 0) / 1e6)

    def _tick_download(self):
        """Called from the window's refresh: report progress, then the outcome."""
        if self._dl['code'] and not self._dl['done']:
            self._show_progress()
            return
        if self._dl['done']:
            code, ok = self._dl['code'], self._dl['ok']
            self._dl['code'] = ''
            # Clear the flag too: the window calls this on every tick, so leaving
            # it set logged the outcome again and again (with an empty code, which
            # is where the bare ": the game files are complete" came from).
            self._dl['done'] = False
            where = ('%s: ' % code) if code else ''
            self.log(where + (tr('dl_complete') if ok else
                              tr('dl_incomplete')))
            self._set_busy(False)
            check_games(force=True)                 # the rows flip when it answers
            self._progress = ''
            self._prog = {}

    def ask_download(self, code, info):
        """The same question the Windows launcher asks before it fetches."""
        from tkinter import messagebox
        if code == 'LPO':
            text = (tr('ask_lpo')
                    % (info.get('bytes_left', 0) / 1e6,
                       info.get('dir') or client_download_dir()))
        else:
            text = (tr('ask_cd')
                    % (max(1, info.get('total', 0) - info.get('present', 0)), code,
                       info.get('bytes_left', 0) / 1e6, info.get('detail', '')))
        return messagebox.askyesno(tr('dn_files'), text)

    def find_client_folder(self, info):
        """The client is nowhere in the server's search order: offer to download
        it, or let the player point at the copy they already have.

        The folder is remembered with save_game_dir() - lpo/game_dir.txt, the file
        lpo/server.py reads at its next start - so the server finds it too.
        """
        from tkinter import filedialog, messagebox
        answer = messagebox.askyesnocancel(
            tr('dn_files'), tr('find_ask') % (info.get('bytes_left', 0) / 1e6))
        if answer is None:
            self.log(tr('no_files_cancel'))
            return False
        if answer:
            return self.run_download('LPO')
        start = str(Path.home())
        for probe in (os.environ.get('LPO_GAME_DIR'),
                      str(Path.home() / 'littleprince-online')):
            if probe and Path(probe).is_dir():
                start = probe
                break
        chosen = filedialog.askdirectory(title=tr('find_title'),
                                         initialdir=start, mustexist=True)
        if not chosen:
            self.log(tr('no_folder_cancel'))
            return False
        chosen = Path(chosen)
        if not has_swfs(chosen):                  # maybe they picked the folder above it
            try:
                for sub in sorted(p for p in chosen.iterdir() if p.is_dir()):
                    if has_swfs(sub):
                        chosen = sub
                        break
            except OSError:
                pass
        if not has_swfs(chosen):
            messagebox.showwarning(tr('dn_files'), tr('no_swf'))
            return False
        save_game_dir(chosen)
        self.log(tr('folder_saved') % chosen)
        check_games(force=True)
        self.launcher.restart_online()
        return True

    def start_pick(self, code):
        """A row of the picker was pressed: fetch that game.

        The row's own code is passed on untouched - the Windows launcher once wired
        its one button to a different game's downloader, which is exactly what this
        shape prevents.
        """
        if self._dl['code'] and not self._dl['done']:
            self.log(tr('dl_running'))
            return
        info = (self._games or {}).get(code)
        if not info:
            self.log(tr('still_checking') % code)
            return
        if info['ready']:
            self.log(tr('already_here') % (code, info['text']))
            return
        if code == 'LPO' and not info.get('found'):
            self.find_client_folder(info)
            return
        if not self.ask_download(code, info):
            self.log(tr('dl_cancelled') % code)
            return
        self.run_download(code)

    def _picker_state(self):
        """What the picker's rows say: each game's own state, and where the client is."""
        games = self._games or check_games()['games']
        rows = {}
        for code, _name in GAMES:
            info = games.get(code)
            rows[code] = ((info['text'], readiness_colour(info)) if info
                          else (tr('v_checking'), launcher_ui.DIM))
        info = games.get('LPO') or {}
        return rows, (tr('online_client') % info['dir'] if info.get('dir') else '')

    def open_picker(self):
        """The four games and what is here; press one to fetch the rest.

        The window is the shared one from launcher_ui - the same palette and the same
        button factory as the launcher itself - so it reads as part of the launcher
        rather than as a second design.  This backend only says what each row says.
        """
        self.check_again()                           # a fresh answer as it opens
        self._picker = launcher_ui.PickerWindow(
            self.ui, tr('dn_files'), tr('picker_sub'),
            [(code, game_label(code)) for code, _name in GAMES],
            self.start_pick, self._picker_state)
        return self._picker


def gui_main():
    """The launcher window - the shared one, with the macOS backend behind it."""
    import tkinter as tk
    tk_ver = tk_report()
    backend = MacBackend(tk_ver=tk_ver)
    root = tk.Tk()
    window = launcher_ui.Window(root, backend)
    if tk_ver < 8.6:
        # Tk 8.5 on macOS often builds the whole window but leaves it unpainted
        # until the window sees a resize event; nudging the size by one pixel and
        # back is the cheapest way to deliver one.  Newer Tk paints on its own.
        def force_redraw():
            geo = root.geometry().split('+')[0]
            w, h = geo.split('x')
            root.geometry('%sx%d' % (w, int(h) + 1))
            root.after(80, lambda: root.geometry(geo))

        root.after(400, force_redraw)
    return window.main()


def main():
    if '--console' in sys.argv:
        return console_main()
    try:
        import tkinter                     # noqa: F401
    except Exception:
        print(tr('no_tk_notice'), file=sys.stderr)
        return console_main()
    try:
        return gui_main()
    except Exception:
        # A window that cannot be built must not take the launcher down with it.
        import traceback
        traceback.print_exc()
        print(tr('no_window_notice'), file=sys.stderr)
        return console_main()


if __name__ == '__main__':
    sys.exit(main())
