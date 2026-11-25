# iOS companion app

DVM Finance has a companion app for **iPhone and iPad**. It's a lightweight
partner to this desktop app: use it to review your transactions, trends, and
budgets on the go, make quick edits and tagging, and then sync those changes
back here. The desktop app remains the home base for bulk statement import,
rule management, and the main database.

The two stay in sync exclusively through **snapshot files** — the same
`.json.gz` snapshots described above. There's no account and no cloud service;
you move the files yourself (AirDrop, Files, iCloud Drive, or email).

## Sync with the QR code

1. Put the computer and the phone on the same Wi-Fi network.
2. In this app, click the **QR icon** in the top bar, next to **Help**. The
   **Export** page opens and shows a QR code.
3. In the iOS app, open the **Import** tab and tap **Sync from computer**.
4. Scan the QR code. The app downloads the snapshot and imports it.

The QR code works for one download only, and it expires after 10 minutes.

### If the sync fails

- **"The QR code expired or was already used"**: click the QR icon again, and
  scan the new QR code.
- **"Couldn't reach your computer"**: make sure that both devices use the same
  Wi-Fi network. Turn off a VPN on the phone. Do not use a guest network. Make
  sure that the firewall of the computer allows incoming connections for
  Python.
- **"DVM Finance needs Local Network access"**: open **Settings › DVM Finance**
  on the phone, and turn on **Local Network**.
- To test the network, scan the QR code with the iPhone Camera app and open the
  link in Safari. If Safari downloads a file, the network is good.

## Getting started with a file: desktop → phone

1. In this app, open the **Export** page from the **⋮** menu.
2. Click **Export snapshot** to download a `.json.gz` file.
3. Get the file onto your device (AirDrop, iCloud Drive, Files, or email).
4. In the iOS app, open the **Import** tab and tap **Import snapshot**, then
   choose the file.
5. Review the import summary — your transactions, categories, rules, and budgets
   are now on your device.

## Pushing changes back: phone → desktop

1. In the iOS app, open the **Import** tab.
2. Under **Export changes since…**, pick the date you last synced (it defaults
   to your previous delta export).
3. Tap **Export delta snapshot** — a small file with only the transactions you
   changed since that date.
4. Share the file back to your computer.
5. Here, open the **Export** page and **import** that file. Incoming changes
   win, your database is backed up first, and the merge is recorded.

## Good to know

- The iOS app can also import raw statement files (MT940, ABN CSV, PayPal, Wise,
  SEB) directly, just like the upload form on the desktop **Import** page.
- A delta snapshot carries only what changed, so it stays small and won't
  overwrite unrelated desktop data. Use a full **Export snapshot** when you want
  to hand off everything.
