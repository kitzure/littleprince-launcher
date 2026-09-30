# Developer notes

## Source versus download package

This repository contains the launcher, local servers, web UI, patch sources,
AMF replay fixtures and development tools. It does not contain player accounts,
private publishing tools, full game payloads or the downloaded Flash runtime.
Use the combined Windows/macOS ZIP from GitHub Releases to install the launcher.

## Main files

- `Start_Server_GUI.pyw`: Windows entry point and backend.
- `LittlePrinceLauncher.command`, `macos/launcher_gui.py`: macOS entry point and backend.
- `launcher_ui.py`: the window shared by both backends.
- `fake_server.py`: local CD-game gateway.
- `lpo/server.py`: HTTP/AMF services and the online game relay.
- `lpo/mp_relay.py`: local multiplayer transport.
- `lpo/pack_download.py`: shared pack download policy.
- `lpo/web/`, `lpo/web.html`: accounts and management pages.

## Download policy

Pack installs use Catbox, Pixeldrain or custom/self-hosted HTTP(S) URLs.
Do not add Google Drive options, fallback IDs or private account links.
Legacy source choices normalize to Auto; Drive custom links and redirects are
rejected before connecting. The publisher's per-file repair paths remain separate.

## Verify changes

From the repository root:

```sh
python3 tools/test_no_drive_downloads.py .
python3 Start_Server_GUI.pyw --selftest --no-hosts --port 18080
```

The regression suite uses a localhost HTTP server and temporary ZIP fixtures;
it does not download the game payload or modify real player accounts.
Rebuild from the full packaging tree using `tools/build_local.py`, then extract
the archive, rerun the tests against it and compare changed file hashes.
Never package accounts, settings, messages, logs or per-player avatar caches.

## More detail

See [HOW-IT-WORKS.md](HOW-IT-WORKS.md) for architecture and features,
[PATCHING.md](PATCHING.md) for patch recipes and [TODO.md](TODO.md) for known issues.
