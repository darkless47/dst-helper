# Runtime images

`images/` contains the 226 Cooking ingredient/dish portraits and three stat icons
used by the app. Include these 229 PNGs in Git so a fresh checkout has pictures
without `wiki-webpage-save/`. Farming currently uses text and color swatches.

Filenames match the existing `/assets/<asset-id>.png` routes, with colons replaced
by hyphens. The loader verifies every PNG against the original SHA-256 recorded
in `DST_Cooking_Data_v0_1/dst_cooking.sqlite` or `data/stat_icons.json`. Original
saved-page paths, source URLs, and artwork rights metadata remain unchanged in
those records; copying files does not establish redistribution rights.

Regenerate from the matching local archive, from the workspace root:

```powershell
python DST_Cooking_Data_v0_1/scripts/package_assets.py wiki-webpage-save
```

This copies only verified runtime images, without downloading anything or copying
HTML, website scripts, styles, tracking files, or unused pictures. Keep the source
archive locally for re-extraction and source audits; it is ignored by Git and is
not needed to run the app.
