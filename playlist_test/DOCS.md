# Playlist test server

This custom app is superseded by the official **Music Assistant DEV SERVER**
configured with the fork sources. Leave this app stopped and follow the
[current test deployment guide](../docs/test-deployment.md).

This is an **unofficial development build**, not Music Assistant 2.10.7.
It includes the matching custom web frontend and runs on amd64 and aarch64.

1. Back up Home Assistant and the official Music Assistant app, including its data.
2. Stop the official Music Assistant app and disable its watchdog and automatic
   startup while testing. **Do not uninstall it.** Both servers use host networking
   and the same ports, so they must not run simultaneously.
3. Start this test app. It has a separate data directory and initially opens the
   setup wizard. Configure the providers and test playlists you need. Your official
   library and credentials are not automatically copied.
4. Open **MA Playlist Test** in the sidebar, or `http://HOME_ASSISTANT_IP:8095`.
   Connect the desktop and Android test clients to that address.
5. Open a playlist's Podcast/Audiobook settings, save the toggles and reopen them.
   Check sorted playback, resume, remaining time, and removal on natural end.
   Use a disposable source playlist: removal changes the provider's real playlist.

To roll back, stop this app and restart the official app. Do not restore a database
written by this development version into 2.10.7. Re-enable the official app's
startup/watchdog settings when finished.

Some providers require application credentials that are licensed only for official
builds. This fork does not redistribute those credentials. Pocket Casts uses your
own login; other providers may need your own registered application credentials.

See [test deployment](../docs/test-deployment.md) for builds, upgrades and clients.
