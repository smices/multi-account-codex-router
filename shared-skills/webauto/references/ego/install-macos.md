# Install ego lite on macOS

Read `install.md` first; it covers onboarding shared by every platform. Download ego lite only from the official site: https://lite.ego.app/ . Use the app's normal installer and keep macOS Gatekeeper enabled.

Before installing, check `/Applications/ego lite.app` and `~/Applications/ego lite.app`. If an existing app is present, do not overwrite or remove it automatically; use the app's own update flow or stop and report that an upgrade is needed. Do not use an installer script that strips quarantine attributes or deletes an existing app.

## Agent installation procedure

If the app is missing, the agent should install it, rather than merely tell the user to download it. Select the macOS arm64 or x64 DMG from the official download page for the current machine. Resolve the current official download URL at installation time; do not guess filenames. Download with `curl --fail --location --proto '=https' --tlsv1.2` into a temporary directory, then mount with `hdiutil attach -readonly -nobrowse -mountpoint` using an empty temporary mount directory.

Find the app bundle in the mounted image. Before copying it, run `codesign --verify --deep --strict --verbose=2` and `spctl --assess --type execute --verbose=2` against that bundle. Stop on verification failure. Create `~/Applications` if necessary, confirm `~/Applications/ego lite.app` is neither an existing file nor a symlink, and copy the bundle there with `ditto`. Verify the installed copy again with the same two checks, detach the image, and launch the installed app with `open`. Clean up only the temporary files created by this installation. Never delete an existing app or strip its security attributes.

After installing, open ego lite and complete first-run onboarding in the app (see `install.md`). Onboarding registers the `ego-browser` command on `PATH`, usually under `~/.local/bin`.

## After installing: confirm `ego-browser` is available

Once the user has finished onboarding, confirm the command is ready:

```bash
command -v ego-browser
```

If it reports that the command isn't found, `~/.local/bin` is most likely not on the current PATH. Fix it temporarily and retry:

```bash
export PATH="$HOME/.local/bin:$PATH"
command -v ego-browser
```

Once the command exists, verify the runtime:

```bash
ego-browser nodejs <<'EOF'
console.log('ego-browser ready')
EOF
```

Printing `ego-browser ready` means the environment is ready. Finally confirm that the installed ego lite prints its usage guide:

```bash
ego-browser skill
```

Then return to the user's original task, as `install.md` describes.

## Troubleshooting

- **Download failed**: check the network and retry from the official site.
- **Gatekeeper blocks the app**: do not remove quarantine or bypass the warning. Verify the download source and follow Apple's current guidance, or stop and report the issue.
- **Command still unavailable after onboarding**: confirm `~/.local/bin` is on the PATH (see above). Otherwise have the user reopen ego lite, finish onboarding, and retry.
