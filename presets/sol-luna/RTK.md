# RTK shell output policy

Use RTK by default for supported shell commands whose textual output will enter
model context. Use `rtk proxy` for exact, machine-readable, piped, redirected,
binary, interactive, or unsupported commands.

- Filter commands before relying on RTK compression.
- Do not use compressed output for parsers, checksums, snapshots, generated
  artifacts, or byte-exact comparisons.
- If RTK is unavailable or rejects a command, fall back once to the narrowest
  safe native command.
- Use `rtk gain` only when token-savings analytics are explicitly requested.
