# Playlist testing with the official Music Assistant DEV SERVER

These builds are maintained in `loic294` forks on `playlist-playback-test`.
They include development server changes, not just patches to stable 2.10.7.
Do not upgrade your only production database in place.

## Home Assistant OS

1. Make a full backup, including Music Assistant, before testing.
2. Use the official repository, `https://github.com/music-assistant/home-assistant-addon`,
   under **Settings > Apps > App store > Repositories**. On older versions these
   menus are named **Add-ons** and **Add-on store**.
3. Install/update **Music Assistant DEV SERVER**. If it is hidden, enable Advanced
   mode in your Home Assistant user profile and reload the store.
4. Leave the former custom **Music Assistant - Playlist Test** app stopped. Keep
   your normal Music Assistant app running.
5. Set the DEV app's configuration to:

   ```yaml
   log_level: info
   safe_mode: false
   server_repo: loic294/server@playlist-playback-test
   frontend_repo: ""
   ```

6. Start the DEV app and wait for the server installation to finish. This can
   take several minutes. Leave `frontend_repo` empty: this server branch installs
   our prebuilt frontend wheel as a pinned, SHA-256-verified dependency.
   Expect `Step 2: Skipping Frontend Build`. This is intentional and still loads
   our UI changes, not the upstream UI.
7. Check the log for `Playlist DEV profile: web port 8195, stream port 8197,
   Sendspin port 9027`.
8. Open **http://HOME_ASSISTANT_IP:8195** directly. On this network that is
   **http://192.168.68.76:8195**. Complete setup in this separate DEV data directory.

The fork activates this fixed network profile only when the official DEV app's
`server_repo` is exactly `loic294/server@playlist-playback-test`. Keep that value,
including its branch name. Other source selections and normal installations keep
their existing ports. The profile overrides previously saved web/stream ports
for this DEV instance at runtime; it does not rewrite saved settings.

| Listener | Normal server | DEV test profile |
| --- | --- | --- |
| Web/API | 8095 | 8195 |
| Audio streams | 8097 | 8197 |
| Sendspin | 8927 | 9027 |
| Home Assistant ingress | 8094 | Disabled |

**Do not use the DEV app's Open Web UI/sidebar link.** The official add-on fixes
that link to ingress port 8094, which belongs to your normal server. Our DEV
profile disables both its ingress listener and ingress-based Home Assistant
auto-announcement to avoid conflicts or accidentally announcing production.
Use the direct URL above; the DEV app's startup log also explains this.

The official DEV app builds and installs the fork server itself. There is no
custom Docker image to build, publish or select. Its own tooling manages the
official image's dependencies and provider application variables.

### Low-memory hosts and frontend updates

On Home Assistant Green, compiling the frontend alongside production caused a
host-wide out-of-memory kill: the kernel killed Node during Vite's `transforming`
phase at roughly 1.29 GiB resident memory. Retrying startup repeats that build.
The warning about Vite's future native config loader is unrelated.

The frontend fork's manual **Publish playlist test frontend** workflow runs tests,
lint, type checking and bundling on GitHub Actions, then publishes a uniquely
versioned Python wheel and checksums in a prerelease. The server's
`pyproject.toml` and generated `requirements_all.txt` point at that exact wheel,
including its SHA-256 hash. The official DEV app installs it without running Node.
No production shutdown, extra swap, or custom Docker image is required.

After frontend changes, run that workflow on `playlist-playback-test`, verify it
succeeds, update the server's wheel URL/hash, regenerate requirements, and push.
Do not use a moving `latest` asset URL. After server or pinned-frontend updates,
restart the DEV app to fetch/install the updated branch. Keep `frontend_repo`
empty, or the official app will build from source again.

To roll back, stop the DEV app. Your normal server and its data remain unchanged.
Do not copy a live database between apps or open a development database with 2.10.7.

## Former custom build

The custom image/app is superseded by the official DEV app. The old Docker
workflow is manual-only and no longer runs on branch pushes. Existing images
remain available, but are not the deployment path described here.

## Desktop

The desktop companion displays the frontend hosted by the selected server.
There is no second copy of playlist logic to implement in Rust.

Use the normal desktop app. In its server selection/settings, connect to
**http://192.168.68.76:8195**, not the normal server at port 8095.
No custom desktop build is necessary.

The earlier desktop test package was not actually isolated: its native settings
path was shared with the normal app, and its official updater could replace it.
Do not rely on that package as an isolated test environment. Connecting the
normal desktop app to the DEV URL loads the custom frontend directly.

## Android

Use the mobile fork's **Android test build** workflow and sideload its APK,
then configure `http://HOME_ASSISTANT_IP:8195`. See the mobile fork's test-build
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
