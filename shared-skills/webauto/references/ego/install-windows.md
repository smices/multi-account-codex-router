# Install ego lite on Windows

Read `install.md` first; it covers upgrading an older ego lite and the onboarding step shared by every platform. This file has the Windows install steps, the commands that confirm the installation, and Windows troubleshooting.

## Run the installer

There is no install script for Windows. Download the installer only from https://lite.ego.app/ . If ego lite is already installed, do not overwrite it; use its official update flow or stop and report that an upgrade is needed. Otherwise run the official installer, then open ego lite. Do not bypass SmartScreen or other platform security warnings based only on this guide.

The agent should download the matching Windows installer from the official page and run it when the app is missing. Before execution, use `Get-AuthenticodeSignature` to check that its status is `Valid` and inspect the publisher; stop if the signature or source is uncertain. Use `Start-Process -FilePath <downloaded-installer> -Wait`, follow the supported installer flow, and leave first-run account choices to the user. Do not invent silent-install flags.

After the app opens, the user completes the first-run onboarding in the app (see `install.md`). Onboarding registers the `ego-browser` command on the PATH. The PATH entry only reaches processes started afterwards, so open a new terminal before checking for the command.

## After installing: confirm `ego-browser` is available

Once the user has finished onboarding, open a new terminal and confirm the command is ready. The command depends on the shell.

PowerShell:

```powershell
Get-Command ego-browser
```

cmd:

```bat
where ego-browser
```

Git Bash:

```bash
command -v ego-browser
```

Once the command exists, verify the runtime. In PowerShell or cmd, where heredoc does not exist:

```powershell
ego-browser nodejs -e "console.log('ego-browser ready')"
```

In Git Bash:

```bash
ego-browser nodejs <<'EOF'
console.log('ego-browser ready')
EOF
```

Printing `ego-browser ready` means the environment is ready. Finally confirm that the installed ego lite prints its usage guide:

```powershell
ego-browser skill
```

Then return to the user's original task, as `install.md` describes.

## Troubleshooting

- **SmartScreen blocks the installer**: verify the installer came from the official ego lite site and check the publisher. If it remains blocked, stop and report the issue rather than bypassing the warning.
- **Command still unavailable after onboarding**: open a new terminal first, because an existing one keeps the PATH it started with. Otherwise have the user reopen ego lite, finish onboarding, and retry.
