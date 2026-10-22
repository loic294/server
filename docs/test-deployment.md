# Unofficial playlist test deployment

These builds are maintained in `loic294` forks on `playlist-playback-test`.
They include development server changes, not just patches to stable 2.10.7.
Do not upgrade your only production database in place.

## Build and image hosting

The [test deployment workflow](https://github.com/loic294/server/actions/workflows/test-deployment.yml)
builds the exact frontend commit in `.github/test-frontend-sha`, runs its tests,
lint and build, packages matching Python wheels, and builds native amd64/arm64
images using the upstream public base image. It does not publish to PyPI or need
any upstream maintainer secrets.

Successful runs publish:

- `ghcr.io/loic294/music-assistant-playlist-test:2.11.0.devN`
- `ghcr.io/loic294/music-assistant-playlist-test:playlist-test` (moving test tag)
- `test-wheels`, containing the two wheels and image requirements.

Each architecture's installed versions and frontend assets are checked before
the manifest and Home Assistant app version are published. Use a numbered tag
for reproducibility. Build labels record both source revisions.

**First publication:** GitHub container packages default to private. In the
package settings, set `music-assistant-playlist-test` to **Public** so Home
Assistant can pull without a registry password. A public repository alone does
not guarantee a public package. Verify an unauthenticated pull before installing.
GitHub Actions must be enabled in the forks, with package write permissions for
this workflow.

For a later frontend change, commit and push it in the frontend fork, replace
`.github/test-frontend-sha` with its full commit SHA, then commit and push the
server branch. Server pushes trigger a build; a manual run rebuilds the current
pinned pair. Never point this file at an uncommitted local frontend.

## Home Assistant OS

1. Make a full backup, including Music Assistant, before testing.
2. Under **Settings > Apps > App store > Repositories**, add
   `https://github.com/loic294/server`. On older Home Assistant versions these
   menus are named **Add-ons** and **Add-on store**.
3. Reload the store after the workflow succeeds. Install **Music Assistant -
   Playlist Test**. Both Intel/AMD 64-bit and ARM64 hosts are supported.
4. Stop the official Music Assistant app, turn off its watchdog and automatic
   startup temporarily, and leave it installed. Only then start the test app.
   They share ports 8094/8095 and cannot run together on the same host.
5. Open the test app's web UI and complete setup. This app has its own data
   directory, so the official server's data is preserved. Configure only the
   providers/playlists you need for the test.

The server fork's **default branch must remain `playlist-playback-test`**:
Home Assistant reads `repository.yaml` and `playlist_test/config.yaml` there.
The workflow updates the offered app version only after both images pass.

To roll back, stop the test app and restart the official 2.10.7 app, restoring
its startup/watchdog settings. Do not point 2.10.7 at a newer development database.
Do not copy a live database between apps.

## Provider credentials

The upstream bundled application credentials are licensed for official builds
only. This pipeline deliberately does not fetch, extract or redistribute them.
Pocket Casts authenticates with your own account. Some other providers require
your own registered application credentials and may not work out of the box.
See `music_assistant/helpers/app_vars.py` for the source-build credential options.
Never commit credentials, tokens, account databases or local configuration.

## Desktop

The desktop companion displays the frontend hosted by the selected server.
There is no second copy of playlist logic to implement in Rust.

Use the normal desktop app and select `http://HOME_ASSISTANT_IP:8095`, or build
the fork:

```sh
cd ../desktop-app
yarn build --bundles app --config src-tauri/tauri.test.conf.json
open "src-tauri/target/release/bundle/macos/Music Assistant Playlist Test.app"
```

The fork's **Desktop test build** workflow also produces an unsigned macOS app
artifact without Apple or updater-signing secrets. Unsigned downloaded builds
may require **Open Anyway** in macOS Privacy & Security. The official desktop
updater still tracks official releases; that is safe because the companion is
unchanged and the custom feature lives on the server.

## Android

Use the mobile fork's **Android test build** workflow and sideload its APK,
then configure `http://HOME_ASSISTANT_IP:8095`. See the mobile fork's test-build
documentation for its app identity and installation instructions. A GitHub
Actions artifact requires signing in to GitHub to download it.

## Acceptance check

Use a disposable playlist and a non-critical player:

- Save and reopen all three Podcast/Audiobook settings.
- Play a resume-enabled playlist in ascending and descending listing order.
- Play an episode/book row and verify the queue retains playlist origin.
- Check remaining time for unstarted, partially played and completed items.
- Finish an item naturally and check source removal when enabled.
- Skip or stop an item and verify it is **not** removed.
- Repeat from desktop and Android against the same test server.

Removal changes the real provider playlist even though the app has a separate
local database. Server unit tests and image checks do not replace a real-device
audio playback test.
