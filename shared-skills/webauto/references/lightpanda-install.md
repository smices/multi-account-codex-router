# Install the Lightpanda runtime

Use the standalone stable `1.0.2` release from the official [GitHub release](https://github.com/lightpanda-io/browser/releases/tag/1.0.2). This is separate from installing this skill. Do not auto-update or use nightly builds unless the user requests them.

Select the asset for the current OS and architecture:

| Asset | SHA-256 |
| --- | --- |
| `lightpanda-aarch64-macos` | `9f3ee749a55d1abc5f8fdda0d9559c3b2abcec5bff5bfe902bc06c0a89538ec4` |
| `lightpanda-x86_64-macos` | `91a775ecc67937d8d79c1b1a315748e52157804f18f629c6e1c6332a46255fc6` |
| `lightpanda-aarch64-linux` | `ac546dfc43c533430da92b75ab36f2a29da7d6324d5d38baf606ef2e0d849345` |
| `lightpanda-x86_64-linux` | `ae7d01d261efb9e480e18ce3424533332883863bcf70b12a4321b5733f37e19e` |

The release assets are hosted at `https://github.com/lightpanda-io/browser/releases/download/1.0.2/<asset>`. Before downloading, check the release's official platform requirements. Linux builds require a compatible glibc; do not assume a distro or architecture is supported if its requirements are unclear. Windows use is through WSL2. Lightpanda in WSL2 and ego-lite in native Windows are separate environments; do not assume they share browser state or can hand off a live session.

On macOS or Linux, select the platform automatically, then download, verify, and install without replacing an existing executable:

```sh
set -eu
case "$(uname -s):$(uname -m)" in
  Darwin:arm64|Darwin:aarch64)
    lp_asset=lightpanda-aarch64-macos
    lp_sha256=9f3ee749a55d1abc5f8fdda0d9559c3b2abcec5bff5bfe902bc06c0a89538ec4 ;;
  Darwin:x86_64)
    lp_asset=lightpanda-x86_64-macos
    lp_sha256=91a775ecc67937d8d79c1b1a315748e52157804f18f629c6e1c6332a46255fc6 ;;
  Linux:aarch64|Linux:arm64)
    lp_asset=lightpanda-aarch64-linux
    lp_sha256=ac546dfc43c533430da92b75ab36f2a29da7d6324d5d38baf606ef2e0d849345 ;;
  Linux:x86_64)
    lp_asset=lightpanda-x86_64-linux
    lp_sha256=ae7d01d261efb9e480e18ce3424533332883863bcf70b12a4321b5733f37e19e ;;
  *) echo 'Unsupported platform; stopping.' >&2; exit 1 ;;
esac
lp_url="https://github.com/lightpanda-io/browser/releases/download/1.0.2/$lp_asset"
lp_tmp=$(mktemp)
trap 'rm -f "$lp_tmp"' EXIT
curl --fail --location --proto '=https' --tlsv1.2 --output "$lp_tmp" "$lp_url"
if command -v shasum >/dev/null 2>&1; then
  lp_actual=$(shasum -a 256 "$lp_tmp" | awk '{print $1}')
elif command -v sha256sum >/dev/null 2>&1; then
  lp_actual=$(sha256sum "$lp_tmp" | awk '{print $1}')
else
  echo 'A SHA-256 utility is required; stopping.' >&2
  exit 1
fi
if [ "$lp_actual" != "$lp_sha256" ]; then
  echo 'SHA-256 mismatch; stopping without installing.' >&2
  exit 1
fi
mkdir -p "$HOME/.local/bin"
lp_target="$HOME/.local/bin/lightpanda"
if [ -e "$lp_target" ] || [ -L "$lp_target" ]; then
  echo "Existing executable found at $lp_target; preserving it. Choose another path or resolve the existing install first." >&2
  exit 1
fi
install -m 0755 "$lp_tmp" "$lp_target"
```

If an executable already exists, keep it and use its reported version; do not overwrite it automatically. To update later, preserve a recoverable copy first and verify the new release checksum before switching.

Add `~/.local/bin` to `PATH` if needed, then inspect `lightpanda version`, `lightpanda help fetch`, and `lightpanda help run`. Confirm real content readback with a small public page, for example:

```sh
LIGHTPANDA_DISABLE_TELEMETRY=true "$HOME/.local/bin/lightpanda" fetch --dump markdown --wait-until networkidle https://example.com
```

Check that the returned Markdown contains the expected page title/content; a successful exit alone does not prove the runtime rendered useful content. If flags differ, follow the installed command's help. For current API and platform requirements, use the official [PandaScript documentation](https://lightpanda.io/docs/usage/pandascript), [CDP/Puppeteer documentation](https://lightpanda.io/docs/usage/cdp/puppeteer), and release page.
