# Google Drive setup (rclone)

Takeout can deliver its archives straight into your Google Drive. The importer then pulls them
with [rclone](https://rclone.org) using an OAuth refresh token — no passwords, cookies or browser
sessions on the server.

You need one rclone token for the Google account that holds the export. There are two ways to
get it:

| | [A. rclone's built-in client](#option-a-rclones-built-in-client-quickest) | [B. Your own OAuth client](#option-b-your-own-oauth-client) |
|---|---|---|
| Google Cloud setup | None | Project, Drive API, consent screen, client |
| Token lifetime | Doesn't expire | Doesn't expire *if the app is In production*; 7 days in *Testing* |
| Rate limits | Shared by every rclone user — can be slower, rclone retries throttled requests | Your own quota |
| Good for | A one-off migration of a handful of large zips | Large or repeated migrations, or if A gets throttled |

Either way you authorize on a machine **with a browser** (your laptop) — the server is headless —
and paste the resulting token into the importer's rclone config.

### Why the full `drive` scope?

Takeout files are created by Google, not by your app. The narrower `drive.file` scope only sees
files your app created, so it cannot list or delete the export. rclone's `drive` scope is required.

## Option A: rclone's built-in client (quickest)

On your laptop (rclone installed locally):

```bash
rclone authorize "drive"
```

Sign in with the account that holds the Takeout export and allow access. rclone prints a JSON
token — copy it, then continue with [Create the rclone config](#create-the-rclone-config-for-the-importer)
and leave out the `client_id` / `client_secret` lines.

## Option B: your own OAuth client

rclone's built-in client is shared by all rclone users and heavily rate-limited; your own client
is faster.

### 1. Google Cloud project and OAuth client

1. Open <https://console.cloud.google.com/> and create a project (e.g. `takeout2immich`).
2. **APIs & Services → Library →** enable **Google Drive API**.
3. **APIs & Services → OAuth consent screen** (Google Auth Platform):
   - User type **External**, app name e.g. `takeout2immich`, your email as support/developer contact.
   - **Audience → Publish app** so the status is **In production**.
     (In *Testing*, only listed test users can sign in — anyone else gets `access_denied` — and
     refresh tokens expire after 7 days, so the importer loses access mid-migration.)
   - You don't need to submit for verification. You'll see an "unverified app" warning when you
     authorize — that's expected for a personal client.
4. **Clients → Create client → Desktop app.** Note the **client ID** and **client secret**.

### 2. Authorize on a machine with a browser

```bash
rclone authorize "drive" "<client_id>" "<client_secret>"
```

Approve in the browser (Advanced → Go to takeout2immich (unsafe) → Allow). rclone prints a JSON
token — copy it.

## Create the rclone config for the importer

The importer reads `/data/importer/secrets/rclone.conf` (on the host:
`$IMPORTER_DATA_PATH/secrets/rclone.conf`). Create it with mode `0600`:

```ini
[gdrive]
type = drive
# Option B only — omit these two lines for rclone's built-in client (option A):
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

## Request the Takeout export

See [quickstart.md, step 4](quickstart.md#4-request-the-export): Google Photos only, `.zip`,
**50 GB** parts, **Add to Drive**, **Export once**.

## Undoing access

Google Account → Security → Third-party access → remove `rclone` (option A) or `takeout2immich`
(option B), and delete `rclone.conf`. For option B the Google Cloud project can be deleted too.

## Notes

- Deleted exports bypass the Drive trash by default (`use_trash: false`), because trash still
  counts against your quota.
- Drive allows ~10 TB/day of downloads per user, far more than any photo export needs.
