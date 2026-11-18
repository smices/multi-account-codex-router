# ego runtime compatibility checks

This is a verification record, not the browser's API contract. Recheck after an ego upgrade; these observations do not establish support in other versions.

## Isolated ephemeral mode check — 2026-11-18

Tested with `ego-browser 0.6.3.14`, Chromium `156.0.8078.96`, and the bundled guide `2.2.1`. Used one newly created, numbered diagnostic TaskSpace without opening account data or importing login state.

| Check | Observed result |
| --- | --- |
| `help("taskSpace")` | Documents `taskSpace(nameOrId, { profileId? })`; no private-mode option. |
| `Target.getBrowserContexts` through `task.cdp()` | Supported. |
| `Target.createBrowserContext` through `task.cdp()` | Creates an isolated context. |
| `Target.createTarget` with that context ID through `task.cdp()` | Rejected: `Target.createTarget is not allowed`. |
| `Target.disposeBrowserContext` | Disposes the diagnostic context successfully. |
| Context count after cleanup | Zero; matches the pre-test count. |

Creating a context alone did not produce a usable isolated ephemeral TaskSpace. The tested CDP path cannot open a page in it, so cross-space session isolation and disposal on exit have not passed end-to-end validation. Ordinary TaskSpaces and persistent Profiles are not accepted substitutes for this mode. This does not establish whether manual incognito windows or future app versions support additional workflows. Do not repeat the blocked call or route it through another CDP entry point.

The official [native binding documentation](https://github.com/citrolabs/ego-lite/blob/f499162d1b911ba9b320ed31b741dba7ebc2e4d6/docs/native-bindings-api.md#await-egocreatetaskspacename-profileid) and [task-space helper](https://github.com/citrolabs/ego-lite/blob/f499162d1b911ba9b320ed31b741dba7ebc2e4d6/package/ego-browser/src/helpers.ts) accept a name and optional profile ID. Upstream [issue 320](https://github.com/citrolabs/ego-lite/issues/320) describes the same context-creation/target-creation gap; the local check above is the evidence for this installed version.

MFA and account login were not exercised in this check.

## Default-mode single-page check — 2026-11-18

Created a numbered TaskSpace, used its initial `p1` to load `https://example.com`, and verified the title and rendered documentation-example content with assertions. The space contained exactly one webpage and required no privacy setup or confirmation. Completion with `task.finish({ keep: [] })` closed the space and its sole managed page, with no preserved unmanaged pages.

The initial check expected a legacy `h1` that the current example page no longer contains. After inspecting the actual snapshot, the final check verified the rendered paragraph instead. This default-mode check establishes normal navigation, reading, single-page use, and space closure; it does not establish isolated browser state or cookie deletion.
