---
name: imagegen
description: How to generate image assets (logos, marks, illustrations) for this repo
---

# Generating image assets

Pick the lightest tool that fits:

1. **Native image generation** — if the agent you're running as has its
   own image tool, prefer it.
2. **Deterministic SVG/CSS** — for logos, UI marks, icons, anything that
   should stay crisp and editable. Hand-write the SVG; no generator needed.
3. **Codex MCP for raster art** — for painterly/photographic work
   (brushwork, mockups, illustrations): open a session with
   `mcp__codex__codex` and use its `image_gen` tool.

## Workflow

- Generate into the session **scratchpad first** — never straight into
  the repo. Review the output (actually look at it) before keeping it.
- Downscale to the sizes the page really displays:
  `sips -Z <px> in.png --out out-<px>.png`
- Commit only the chosen small variants into the repo with clear names
  and a stated home (e.g. `tools/assets/guide-enso-96.png`); large
  masters stay in the scratchpad.
- Keep every kept output inside the repo — no external hosting; the
  shelf inlines them as data: URIs to stay self-contained.

## Working recipe (2026-07)

codex MCP session → `image_gen` prompt → review PNG in scratchpad →
`sips -Z 320` / `sips -Z 96` for display sizes → commit the small
variants to `tools/assets/`.
