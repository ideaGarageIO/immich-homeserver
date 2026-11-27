# Quickstart

This gets a Google Photos library into Immich with the importer running next to Immich in
Docker Compose. Budget about 30 minutes of setup; the export itself takes Google hours to days.

## Before you start

- A running Immich (v3.x) installed with Docker Compose.
- Free disk space on the server roughly equal to your library size (for staging).
- **Google storage with room for a second copy of your library.** Takeout writes the export into
  your own Google Drive, and it counts against your Google One quota. If you're short, upgrade
  for a month and downgrade afterwards (the importer reminds you).

## 1. Add the importer to your compose project

Copy `immich-importer/` next to your `docker-compose.yml` and add the `immich-importer` service
from [`deployment/docker-compose.yml`](../../deployment/docker-compose.yml). Add to `.env`:

```ini
IMPORTER_STAGING_PATH=/path/to/large/disk/takeout
IMPORTER_DATA_PATH=./importer-data
IMPORTER_UID=1000   # owner of the two paths above (`id -u`)
IMPORTER_GID=1000
```

```bash
docker compose up -d --build immich-importer
```

## 2. Create the credentials

1. **Immich API key:** Immich → Account Settings → API Keys → New. Give it at least
   `asset.upload`, `asset.read`, `album.create`, `album.update`, `tag.create`, `tag.asset`,
   `job.create`, `server.about` — or simply *All*.
2. **Google Drive access for rclone:** follow [google-drive-setup.md](google-drive-setup.md).
   The quickest route is `rclone authorize "drive"` on your laptop with rclone's built-in client —
   no Google Cloud project needed.
3. *(Optional)* **Home Assistant:** Profile → Security → Long-lived access tokens → Create.

## 3. Configure

```bash
docker compose exec immich-importer t2i config
```

Fill in **Immich** (URL `http://immich-server:2283`, API key), **Source** (`drive`, your rclone
remote name) and **Notifications**, pressing **Test** on each screen. Then:

```bash
docker compose exec immich-importer t2i doctor
```

Everything should be `OK`.

## 4. Request the export

At <https://takeout.google.com>:

1. **Deselect all**, then select only **Google Photos** (all albums).
2. Next step: **Transfer to: Add to Drive**, **Frequency: Export once**,
   **File type: .zip**, **File size: 50 GB**.
3. **Create export.**

The importer notices parts as Google writes them into `My Drive/Takeout` and downloads them as
they appear. `t2i status` shows progress.

## 5. Confirm when Google says it's done

Google emails "Your Google data is ready". Then either press **Confirm export complete** on the
TUI Status screen or run:

```bash
docker compose exec immich-importer t2i confirm
```

The importer downloads any last parts, imports everything with immich-go, validates every file
against Immich, and — only if validation passes — deletes the zips and the Drive copy.

## 6. Afterwards

- Read the validation report (`t2i status` shows the path; the TUI has **View report**).
- Downgrade your Google One plan if you upgraded for the migration.
- Deleting photos from Google Photos is up to you; the importer never touches Google Photos.
