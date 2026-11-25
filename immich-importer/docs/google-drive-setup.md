# Google Drive setup (rclone + your own OAuth client)

Takeout can deliver its archives straight into your Google Drive. The importer then pulls them
with [rclone](https://rclone.org) using an OAuth refresh token — no passwords, cookies or browser
sessions on the server.

You create your **own** Google Cloud OAuth client. rclone's built-in client is shared by all rclone
users and is heavily rate-limited; your own client is faster and, set to *In production*, its
refresh token does not expire after 7 days.

## 1. Google Cloud project and OAuth client

1. Open <https://console.cloud.google.com/> and create a project (e.g. `takeout2immich`).
2. **APIs & Services → Library →** enable **Google Drive API**.
3. **APIs & Services → OAuth consent screen** (Google Auth Platform):
   - User type **External**, app name e.g. `takeout2immich`, your email as support/developer contact.
   - **Audience → Publish app** so the status is **In production**.
     (In *Testing*, refresh tokens expire after 7 days and the importer loses access mid-migration.)
   - You don't need to submit for verification. You'll see an "unverified app" warning when you
     authorize — that's expected for a personal client.
4. **Clients → Create client → Desktop app.** Note the **client ID** and **client secret**.

### Why the full `drive` scope?

Takeout files are created by Google, not by your app. The narrower `drive.file` scope only sees
files your app created, so it cannot list or delete the export. rclone's `drive` scope is required.

## 2. Authorize on a machine with a browser

The server is headless, so mint the token on your laptop (rclone installed locally):

```bash
rclone authorize "drive" "<client_id>" "<client_secret>"
```

Approve in the browser (Advanced → Go to takeout2immich (unsafe) → Allow). rclone prints a JSON
token — copy it.

## 3. Create the rclone config for the importer

The importer reads `/data/importer/secrets/rclone.conf` (on the host:
`$IMPORTER_DATA_PATH/secrets/rclone.conf`). Create it with mode `0600`:

```ini
[gdrive]
type = drive
client_id = <client_id>
client_secret = <client_secret>
scope = drive
token = <paste the JSON token here, on one line>
```

```bash
chmod 600 importer-data/secrets/rclone.conf
docker compose exec immich-importer rclone --config /data/importer/secrets/rclone.conf lsd gdrive:
```

You should see your Drive folders. Then in `t2i config` → **Source**: type `drive`, remote
`gdrive`, folder `Takeout`, and press **Test**.

## 4. Request the Takeout export

See [quickstart.md, step 4](quickstart.md#4-request-the-export): Google Photos only, `.zip`,
**50 GB** parts, **Add to Drive**, **Export once**.

## Undoing access

Google Account → Security → Third-party access → remove `takeout2immich`, and delete
`rclone.conf`. The Google Cloud project can be deleted too.

## Notes

- Deleted exports bypass the Drive trash by default (`use_trash: false`), because trash still
  counts against your quota.
- Drive allows ~10 TB/day of downloads per user, far more than any photo export needs.
