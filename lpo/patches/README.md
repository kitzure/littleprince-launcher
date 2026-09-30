# LPO patch layer

The SWF binaries this layer produces (`lib.*.swf`, `lib_resMaze.swf`, `lpo/lib/lib.swf`)
are **not committed** — they are patched copies of the publisher's `lib.swf`, which is
not ours to redistribute. Only the patch sources and notes live here.

## Patch sources

| File | What it does |
|---|---|
| `CastleHall.board-forward.as` | ActionScript for the board/hall forward action |
| `MapForestMaze.door-open.as` | ActionScript that opens the forest maze door |

## Rebuilding

The scripts that produced the patched SWFs live in [`../../tools/swf-build/`](../../tools/swf-build/).
The general flow is:

1. Export the class tree of the publisher's `lib.swf` with JPEXS Free Flash
   Decompiler (FFDec).
2. Apply the `.as` sources above (and the targeted edits in the `tools/swf-build/`
   scripts) to the exported scripts.
3. Rebuild the SWF with FFDec and verify it against the original before shipping.
4. Drop the rebuilt `lib.swf` into the local client's `lpo/patches/`-equivalent
   location so the relay serves it.

Which patch is which, and how to verify a rebuild, is described in
[`../../PATCHING.md`](../../PATCHING.md).
