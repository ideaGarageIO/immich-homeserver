# Sources

A source is where Takeout archives come from. Choose one with `source.type`.

| Type | Status | Needs Google storage? | Unattended? |
|---|---|---|---|
| `drive` | ✅ supported | Yes — a second copy of the export | Yes, after one Takeout request and one confirmation |
| `local` | ✅ supported | No | You download the zips yourself |
| `direct` | 🚧 planned | No | Planned |

## `drive` — Takeout → Google Drive → rclone (recommended)

Takeout writes the export into `My Drive/Takeout`. The importer lists that folder with rclone,
downloads each part as soon as it appears (Drive only shows a file once it is fully written),
checks its MD5, and after a successful validation deletes it permanently.

Why this is the recommended path: Google's direct download links require a signed-in browser and
force re-authentication about every hour, allow only ~5 downloads per part, and expire after
7 days. Drive downloads use an OAuth refresh token and have none of those limits.

The cost: while the export sits in Drive it uses your Google One quota (about the size of your
library). Setup: [google-drive-setup.md](google-drive-setup.md).

## `local` — archives already on disk

Point `source.path` at a folder with `takeout-*.zip` files (downloaded by hand, from another
machine, or from an older export). The files are read in place — not copied — and are only
deleted if you set `delete_originals: true`. By default the import starts as soon as the files
are found (`auto_confirm: true`); set it to `false` if you are still copying files in.

## `direct` — planned

Downloading straight from Google's Takeout links would need no Google storage, which matters
when your account is full. It requires browser automation that gets through Google's frequent
"verify it's you" prompts, and that is fragile and can trigger account security checks. It is not
implemented yet; selecting it makes `doctor` and the worker report that clearly.

## Other routes that don't work (as of 2026)

- **Google Photos Library API** (and rclone's `googlephotos` backend): since March 2025 it only
  returns media uploaded by the same app, so it cannot read your library.
- **Google Data Portability API**: only available for accounts associated with the EEA, UK or
  Switzerland. Eligibility follows the account's country association, not your IP address, so a
  VPN doesn't help.
