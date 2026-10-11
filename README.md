# YT-Long

**Version 0.2.5**

Batch-set the title, description and visibility of videos you have already
uploaded to YouTube, using the official YouTube Data API.

## What it does

You upload the videos yourself in YouTube Studio (drag and drop, they land as
drafts). This tool then fills in the boring part for all of them at once:

- **Title**: whatever you type per video in a spreadsheet (`titles.csv`).
  Rows you leave blank get `<YOUR TITLE PREFIX> #1`, `#2`, ...
- **Description**: the video's original filename, then your own text under it:

  ```
  <ORIGINAL FILENAME>
  <YOUR VIDEO DESCRIPTION>
  ```

- **Visibility** (optional): draft/private to public, unlisted or private.

It does not upload videos. Uploads made through the API by an unverified app
are locked to private by YouTube, so uploading stays in Studio.

### Example

Say your phone named three clips `IMG_3897.MOV`, `IMG_3898.MOV` and
`IMG_3899.MOV`. You upload them, type a title for the first two, leave the
third blank, and run:

```bash
python yt_batch.py apply --pattern "^IMG_" --prefix "Trip" --line "Shot on my phone"
```

| File | Title you typed | Title on YouTube | Description on YouTube |
| --- | --- | --- | --- |
| `IMG_3897.MOV` | Sunrise at the summit | Sunrise at the summit | `IMG_3897`<br>`Shot on my phone` |
| `IMG_3898.MOV` | Walking down | Walking down | `IMG_3898`<br>`Shot on my phone` |
| `IMG_3899.MOV` | *(blank)* | Trip #1 | `IMG_3899`<br>`Shot on my phone` |

## 1. Install

```bash
git clone https://github.com/LordsLumingz/YT-Long.git
cd YT-Long
```

**Windows:** double-click `install.bat`. It installs Python with winget if
you do not have it, then installs the modules the tool needs. If it says
Python cannot be seen yet, close the window and run it once more.

**Anything else, or by hand:** install Python 3.10 or newer, then:

```bash
pip install -r requirements.txt
```

## 2. Get a Google API login file (once)

The tool needs your own OAuth client file. It is not in this repo and must
never be committed.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a
   project.
2. **APIs & Services > Library**: enable **YouTube Data API v3**.
3. **APIs & Services > OAuth consent screen**: set it up as **External**, and
   add your own Google address under **Test users**.
4. **APIs & Services > Credentials > Create credentials > OAuth client ID**,
   application type **Desktop app**.
5. Download the JSON. Keep its name (`client_secret_....json`) and put it in
   this folder, or in the folder one level above it.

The first command you run opens a browser to log in. Pick the Google account
that owns the channel and allow access. The login is saved to `token.json`.

## 3. How to use

Replace the `<...>` parts with your own values. Use the same `--pattern` on
`export` and on every `apply`.

1. **Upload** your videos in YouTube Studio and leave them as drafts.

2. **Export** the list of videos:

   ```bash
   python yt_batch.py export --pattern "^<FILENAME PREFIX>"
   ```

   This writes `titles.csv` with one row per private video whose original
   filename starts with `<FILENAME PREFIX>`. Leave `--pattern` out to list
   every private video on the channel.

3. **Type your titles** in the `title` column of `titles.csv` (Excel is fine)
   and save. Do not change the `video_id` column.
   - A row left blank gets an automatic title: `<YOUR TITLE PREFIX> #1`, ...
   - A row left blank whose video already has a real title is skipped.

4. **Preview**. Nothing is changed:

   ```bash
   python yt_batch.py apply --pattern "^<FILENAME PREFIX>" --prefix "<YOUR TITLE PREFIX>" --line "<YOUR VIDEO DESCRIPTION>" --dry-run
   ```

5. **Test on one video**: same command with `--limit 1` in place of
   `--dry-run`. Then check that video in Studio.

6. **Apply to all**: same command with neither `--dry-run` nor `--limit`.

7. **Publish** (optional). Add these to the command to set the videos public
   and declare them not made for kids:

   ```bash
   python yt_batch.py apply --pattern "^<FILENAME PREFIX>" --visibility public --not-for-kids
   ```

Running `apply` again is safe: finished videos are logged in `done.json` and
skipped.

## 4. Commands

| Command | What it does |
| --- | --- |
| `export` | List your videos and write `titles.csv`. Titles you already typed are kept when you export again. |
| `apply` | Read `titles.csv` and update each video. |
| `help` or `?` | Show all commands and options. Same as no command, `-h` or `--help`. |
| `version` | Print the version. Same as `-V` or `--version`. |

Options for `export` and `apply`:

| Option | Default | What it does |
| --- | --- | --- |
| `--pattern REGEX` | all videos | Only include videos whose original filename matches. See the table below. |
| `--line TEXT` | none | Your text, added to every description under the filename. |
| `--prefix TEXT` | `Video` | Title prefix for rows left blank: `Video #1`, `Video #2`, ... |
| `--any-visibility` | off | Include videos that are not private. |
| `--deep` | off | Also search for drafts missing from the uploads list. Costs more quota. |

What to write for `--pattern` (keep the quotes):

| You want | Write | Matches |
| --- | --- | --- |
| Filenames that start with `IMG_` | `--pattern "^IMG_"` | `IMG_3897.MOV` |
| Filenames that start with `VID` | `--pattern "^VID"` | `VID20260101.mp4` |
| Filenames that end with `.MOV` | `--pattern "\.MOV$"` | `IMG_3897.MOV`, `clip.MOV` |
| Filenames that contain `gopro` | `--pattern "gopro"` | `my_gopro_01.mp4` |
| Everything | leave `--pattern` out | all your private videos |

`^` means "starts with" and `$` means "ends with". The match is on the name
the file had on your computer when you uploaded it, not on the YouTube title.

Options for `apply` only:

| Option | What it does |
| --- | --- |
| `--dry-run` | Print what would change, change nothing. |
| `--limit N` | Only update the first N pending videos. |
| `--visibility V` | Also set visibility: `public`, `unlisted` or `private`. |
| `--not-for-kids` | Declare the videos not made for kids. Needed to publish a draft. |

## 5. What to double-check

Before `apply`:

- **Run `--dry-run` first** and read every line. It shows the exact title and
  description each video will get.
- **Row count.** `export` picks up every private video that matches
  `--pattern`, not only the batch you just uploaded. Leave the `title` blank
  on old videos you do not want touched, or delete those rows.
- **Descriptions are replaced, not appended.** Any description already on a
  video in the list is overwritten.
- **Titles are at most 100 characters.** The tool stops if one is longer.
- **Save `titles.csv` as CSV**, not `.xlsx`, and keep the header row.
- **`--line` and `--prefix` are not remembered.** Pass them on every `apply`;
  without `--line` the description is only the filename.

Before publishing:

- **`--not-for-kids` is your legal declaration** about the content. Only use
  it if it is true for every video in the list.
- **Public is immediate.** Subscribers can be notified as soon as a video goes
  public. Use `--limit 1` first, or `--visibility unlisted` to stage.
- **Videos have finished processing** in Studio.

After a run:

- **Refresh Studio with Ctrl+F5.** The list view often shows old titles for a
  while.
- **Quota.** Each update costs 50 units out of 10,000 per day, about 200
  videos. If it runs out, the tool stops; run the same command the next day.
- **Login expiry.** While the Google app is in "Testing" mode the login lasts
  7 days. After that the browser login opens again.
- **`Error 403: access_denied` at login** means the Google account is not
  listed under Test users (step 2.3).

## 6. Files

| File | What it is | In git |
| --- | --- | --- |
| `yt_batch.py` | The tool. | yes |
| `install.bat` | Windows setup: Python and the modules. | yes |
| `requirements.txt` | The Python modules the tool needs. | yes |
| `titles.csv` | Your video list and titles. | no |
| `done.json` | Log of finished videos. Delete an entry to redo that video. | no |
| `token.json` | Your saved login. Treat it like a password. | no |
| `client_secret_*.json` | Your Google OAuth client. Treat it like a password. | no |

To revoke the tool's access, remove the app at
[myaccount.google.com/permissions](https://myaccount.google.com/permissions).
