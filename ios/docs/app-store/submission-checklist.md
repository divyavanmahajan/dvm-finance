# App Store submission checklist — DVM Finance (iOS)

Everything below that lives in the repo is already done. The remaining items
require an Apple Developer account and App Store Connect, which cannot be
automated from here — they are listed with exact steps.

## 1. Prerequisites (one-time, outside the repo)

- [ ] **Apple Developer Program** membership ($99/yr) — https://developer.apple.com/programs/
- [ ] In Xcode ▸ Settings ▸ Accounts, add your Apple ID.
- [ ] Set your team: open `project.yml`, put your 10-char Team ID in
      `DEVELOPMENT_TEAM`, then run `xcodegen generate`. (Or set it in Xcode ▸
      target ▸ Signing & Capabilities — but re-running xcodegen will clear it,
      so prefer `project.yml`.)
- [ ] Register the bundle id **`com.dvm.finance`** at
      https://developer.apple.com/account/resources/identifiers (Xcode's
      automatic signing will offer to do this on first archive).

## 2. In-repo build config — DONE

- [x] `TARGETED_DEVICE_FAMILY = 1,2` (iPhone + iPad)
- [x] `UIRequiresFullScreen = YES` (runs full screen on iPad; clears the
      "all interface orientations" warning)
- [x] `MARKETING_VERSION = 1.0.0`, `CURRENT_PROJECT_VERSION = 1`
- [x] `ITSAppUsesNonExemptEncryption = NO` (skips the export-compliance prompt)
- [x] `LSApplicationCategoryType = public.app-category.finance`
- [x] `PrivacyInfo.xcprivacy` — no tracking, no data collection, no
      required-reason APIs (GRDB ships its own manifest)
- [x] App icon: 1024×1024 in `Assets.xcassets/AppIcon.appiconset` (single-size,
      Xcode derives the rest)

## 3. App Store Connect setup

- [ ] Create the app record at https://appstoreconnect.apple.com ▸ My Apps ▸ +
      ▸ New App. Platform: iOS. Bundle ID: `com.dvm.finance`. SKU: `dvm-finance-001`.
- [ ] Fill in the listing from [`metadata.md`](./metadata.md).
- [ ] Host [`privacy-policy.md`](./privacy-policy.md) at a public URL and paste
      it into App Privacy ▸ Privacy Policy URL. (A privacy policy URL is
      mandatory even for apps that collect nothing — e.g. a GitHub Pages page.)
- [ ] Answer the **App Privacy** questionnaire: "Data Not Collected" for every
      category (the app stores everything locally and transmits nothing).
- [ ] **Age rating** questionnaire → expected **4+**.
- [ ] Upload screenshots (see requirements in [`metadata.md`](./metadata.md)).

## 4. Archive & upload

```bash
cd ios
# make sure DEVELOPMENT_TEAM is set in project.yml first, then:
xcodegen generate
xcodebuild -project DVMFinance.xcodeproj -scheme DVMFinance \
  -destination 'generic/platform=iOS' \
  -archivePath build/DVMFinance.xcarchive archive
xcodebuild -exportArchive -archivePath build/DVMFinance.xcarchive \
  -exportPath build/export -exportOptionsPlist ExportOptions.plist
```

Or simply: Xcode ▸ Product ▸ Destination "Any iOS Device" ▸ Product ▸ Archive
▸ Organizer ▸ Distribute App ▸ App Store Connect ▸ Upload. (Easiest for a
first submission — it handles signing and `ExportOptions.plist` for you.)

- [ ] After the build finishes processing in App Store Connect (~10–30 min),
      attach it to the 1.0.0 version.
- [ ] Complete "Export Compliance" — already answered via the Info.plist key,
      so no prompt should appear.
- [ ] Submit for review.

## 5. Bumping versions later

- New **build** of the same version: increment `CURRENT_PROJECT_VERSION`.
- New **release**: bump `MARKETING_VERSION` (and create the version in App Store
  Connect). Then `xcodegen generate` and re-archive.
