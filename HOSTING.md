# Hosting Card Tracker online (so your PC doesn't need to be on)

**Cost:** you need a host with a *persistent disk* (so accounts and collections survive restarts). Free tiers
that sleep or wipe their disk (e.g. Render's free plan) will lose everyone's data. Expect roughly **$5/month**
(Railway Hobby, plus a few cents for the disk). Check the host's pricing page for the current numbers.

**Memory:** the app uses about 300-400 MB. Pick a plan with at least 1 GB to be safe (price history downloads
use extra memory briefly).

## Part A - on your PC (once)
1. Let `update_catalog.bat` finish if you can. (If not, the server tops up the missing cards itself,
   slowly, in the background.)
2. Double-click **`export_catalog.bat`**. It creates `data\catalog.db.gz` (about 45 MB). It contains **only**
   the card catalogue: no accounts, collections or photos.
3. On GitHub open your repository -> **Releases** -> **Create a new release**. Tag: `catalog-v1`. Drag
   `catalog.db.gz` into the box. **Publish release**.
4. Right-click the `catalog.db.gz` file on the release page -> **Copy link address**. Keep that link; it
   looks like `https://github.com/<you>/pokemon-card-scanner/releases/download/catalog-v1/catalog.db.gz`.

## Part B - Railway (about 10 minutes; screens may differ slightly)
1. Go to railway.com, sign in with GitHub, **New Project** -> **Deploy from GitHub repo** -> pick
   `pokemon-card-scanner`. In the service's **Settings**, set the branch to **`Ishan`**. Railway finds the
   `Dockerfile` and builds it (the first build takes several minutes).
2. **Add a Volume** to the service and set its mount path to **`/data`**.
3. Open **Variables** and add:
   - `CATALOG_URL` = the link from step A4
   - `SIGNUP_CODE` = an invite code you make up (letters and numbers)
   - `MAX_USERS` = `10` (optional; 10 is the default)
4. **Settings -> Networking -> Generate Domain.** That is your permanent web address.
5. Open it. The first start loads the catalogue (about a minute). Visit `/healthz` on your address: it should
   show `{"ok":true,"cards":...}`.

## Part C - first use
1. Open your address and **create your own account first**, using your invite code.
2. Send friends the address and the invite code (up to 10 accounts).
3. Updating the app later: when new code lands on the `Ishan` branch, Railway rebuilds and redeploys by itself.
   Accounts and collections live on the volume and are kept.

## Good to know
- The hosted copy starts **empty**: your collection on your PC isn't moved over. Re-add cards (scan, or search).
- Price history downloads in the background for cards people add, same as on your PC.
- Backups: the volume is the only copy of accounts and collections. Ask me to add a backup/export feature
  if you want one.
- Everything is HTTPS (the host provides it). Passwords are stored scrambled; sign-ups need the invite code;
  repeated wrong passwords lock that visitor out for 15 minutes.
- Other hosts work with the same `Dockerfile`: set the same two variables, mount a disk at `/data`.
