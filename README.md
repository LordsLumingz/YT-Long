# YT-Long

**Version 0.3.7**

Batch-set the title, description, visibility and playlist of videos you have
already uploaded to YouTube, using the official YouTube Data API.

New in 0.3.7:

- `playlist` command and `apply --playlist`: list your playlists, add videos
  to one, create it if it is missing.
- `export --title-pattern`, `--in-playlist` and `--untitled`: pick videos by
  their current title, by playlist, or only the ones not titled yet.
- `apply` changes only what you ask for in that run, so the steps can be done
  one at a time and in any order. `--force` redoes a change.
- `titles.csv` has a `url` column, used when Excel damages a video id.

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
- **Playlist** (optional): add all of them to a playlist, creating it if it
  does not exist yet.

It does not upload videos. Uploads made through the API by an unverified app
are locked to private by YouTube, so uploading stays in Studio.

### Example

Say your phone named three clips `IMG_3897.MOV`, `IMG_3898.MOV` and
`IMG_3899.MOV`. You upload them, type a title for the first two, leave the
third blank, and run:

```bash
python yt_batch.py export --pattern "^IMG_"
python yt_batch.py apply --prefix "Trip" --line "Shot on my phone"
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

Replace the `<...>` parts with your own values. `export` decides which videos
go into `titles.csv`; `apply` then touches exactly the rows in that file.

1. **Upload** your videos in YouTube Studio and leave them as drafts.

2. **Export** the list of videos:

   ```bash
   python yt_batch.py export --pattern "^<FILENAME PREFIX>"
   ```

   This writes `titles.csv` with one row per private video whose original
   filename starts with `<FILENAME PREFIX>`. Leave `--pattern` out to list
   every private video on the channel.

   `export` rewrites `titles.csv` from scratch each time. Titles you typed
   are kept for videos that are still in the list; rows for videos that no
   longer match are dropped. Add `--untitled` to list only videos you have
   not titled yet.

3. **Type your titles** in the `title` column of `titles.csv` (Excel is fine)
   and save. Do not change the `video_id` or `url` columns.
   - A row left blank gets an automatic title: `<YOUR TITLE PREFIX> #1`, ...
   - A row left blank whose video already has a real title keeps its title
     and description.

4. **Preview**. Nothing is changed:

   ```bash
   python yt_batch.py apply --prefix "<YOUR TITLE PREFIX>" --line "<YOUR VIDEO DESCRIPTION>" --dry-run
   ```

5. **Test on one video**: same command with `--limit 1` in place of
   `--dry-run`. Then check that video in Studio.

6. **Apply to all**: same command with neither `--dry-run` nor `--limit`.

7. **Publish** (optional). Add these to the command to set the videos public
   and declare them not made for kids:

   ```bash
   python yt_batch.py apply --prefix "<YOUR TITLE PREFIX>" --line "<YOUR VIDEO DESCRIPTION>" --visibility public --not-for-kids
   ```

8. **Put them in a playlist** (optional). See what you already have, then add:

   ```bash
   python yt_batch.py playlist
   ```

   This writes `playlist.csv`: playlist title, visibility, number of videos
   and playlist id.

   ```bash
   python yt_batch.py apply --playlist "<YOUR PLAYLIST NAME>" --dry-run
   ```

   Drop `--dry-run` to do it. If no playlist has that name, a new private one
   is created. Videos are added in `titles.csv` order, and a video already in
   the playlist is not added again.

You do not have to follow that order or put everything in one command. Each
`apply` run changes only what you ask for in that run and leaves everything
else on the video as it is:

| You run | What changes |
| --- | --- |
| `apply` | Titles you typed in `titles.csv`. A video nobody has titled yet also gets `Video #N` if its row is blank, and its filename as description. |
| `apply --line "text"` | The description: filename, then your text. Titles stay. |
| `apply --prefix "Trip"` | The automatic titles become `Trip #N`. Typed titles stay. |
| `apply --visibility public` | Only the visibility. |
| `apply --not-for-kids` | Only the made-for-kids declaration. |
| `apply --playlist "Name"` | Only the playlist. |

So typing a new title in `titles.csv` later and running `apply` again renames
just that video; its description, visibility and playlist are not touched.
Rows are matched to videos by `video_id`, so the `current_title` column being
out of date does not matter. Running the same command twice is safe: a change
that is already in place is skipped.

## 4. Commands

| Command | What it does |
| --- | --- |
| `export` | List your videos and write `titles.csv`. Titles you already typed are kept when you export again. |
| `apply` | Read `titles.csv` and update each video. |
| `playlist` | Write your playlists to `playlist.csv`: title, visibility, number of videos, id. Same as `getplaylist`. |
| `help` or `?` | Show all commands and options. Same as no command, `-h` or `--help`. |
| `version` | Print the version. Same as `-V` or `--version`. |

Options for `export` (which videos go into `titles.csv`):

| Option | Default | What it does |
| --- | --- | --- |
| `--pattern REGEX` | all videos | Only include videos whose original filename matches. See the table below. |
| `--title-pattern REGEX` | all videos | Only include videos whose **current YouTube title** matches. Studio turns `IMG_3897.MOV` into the title `IMG 3897`, so write `"^IMG "` with a space, not `"^IMG_"`. |
| `--in-playlist NAME` | all videos | Only include videos that are in this playlist of yours. Run `playlist` to see the names. |
| `--untitled` | off | Only include videos nobody has titled yet: the title is still the one YouTube made from the filename. |
| `--any-visibility` | off | Include videos that are not private. |
| `--deep` | off | Also search for drafts missing from the uploads list. Costs more quota. |

What to write for `--pattern` (keep the quotes):

| You want | Write | Matches |
| --- | --- | --- |
| Filenames that start with `IMG_` | `--pattern "^IMG_"` | `IMG_3897.MOV` |
| Filenames that start with `VID` | `--pattern "^VID"` | `VID20260101.mp4` |
| Filenames that end with `.MOV` | `--pattern "\.MOV$"` | `IMG_3897.MOV`, `clip.MOV` |
| Filenames that contain `gopro` | `--pattern "gopro"` | `my_gopro_01.mp4` |
| `Merbabu` **or** `Lawu` | `--title-pattern "Merbabu\|Lawu"` | either word |
| `merbabu` in any capitalisation | `--title-pattern "(?i)merbabu"` | `Merbabu`, `merbabu`, `MERBABU` |
| Everything | leave `--pattern` out | all your private videos |

`^` means "starts with", `$` means "ends with", `|` means "or", and `(?i)` at
the front means "ignore upper/lower case". The same rules work in
`--title-pattern`. The filters stack: a video must pass every one you give.

`--pattern` matches the name the file had on your computer when you uploaded
it. `--title-pattern` matches the title the video has on YouTube now.

Options for `apply`:

| Option | What it does |
| --- | --- |
| `--line TEXT` | Rewrite the description: filename, then your text under it. Without it, descriptions the tool already set are left alone. |
| `--prefix TEXT` | Title prefix for rows left blank: `Video #1`, `Video #2`, ... Default: `Video`. |
| `--dry-run` | Print what would change, change nothing. |
| `--force` | Redo the changes even if they look already done, for example after you changed something back in Studio. |
| `--limit N` | Only update the first N pending videos. |
| `--visibility V` | Set visibility on every row: `public`, `unlisted` or `private`. |
| `--not-for-kids` | Declare the videos not made for kids. Needed to publish a draft. |
| `--playlist NAME` | Add every row to this playlist. Created if no playlist has that name. |
| `--playlist-visibility V` | Visibility of a newly created playlist: `public`, `unlisted` or `private`. Default: `private`. |

## 5. What to double-check

Before `apply`:

- **Run `--dry-run` first** and read every line. It shows the exact title and
  description each video will get.
- **Row count.** `export` picks up every private video that matches
  `--pattern`, not only the batch you just uploaded. Delete the rows of
  videos you do not want touched: `--visibility`, `--not-for-kids` and
  `--playlist` act on every row in the file, with or without a title.
- **`--line` replaces the description, it does not append.** Whatever was in
  the description of those videos is overwritten with filename + your text.
- **Type the `--line` text by hand.** Text copied from Windows file
  properties (dates especially) carries invisible characters. They end up in
  the description and show in the preview as `\u200e` or `\u200f`.
- **Titles are at most 100 characters.** The tool stops if one is longer.
- **Save `titles.csv` as CSV**, not `.xlsx`, and keep the header row.
- **Excel and video ids.** Excel reads an id that starts with `-` or `=` as a
  formula and saves it as `#NAME?`, even if you never click the cell. The
  `url` column holds the same id and the tool uses it instead, so leave both
  columns alone. A `titles.csv` made by a version before 0.3.7 has no `url`
  column: retype that id with an apostrophe in front (`'-abc...`), or the
  video is reported as "not found" and skipped.
- **Playlist name.** Run `playlist` first and check `playlist.csv`. A typo in
  `--playlist` creates a new playlist instead of using the one you meant.

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
  videos. Adding a video to a playlist costs another 50. If it runs out, the
  tool stops; run the same command the next day.
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
| `playlist.csv` | Your playlists, written by `playlist`. | no |
| `done.json` | Log of what the tool has set on each video. Use `--force` to redo. | no |
| `token.json` | Your saved login. Treat it like a password. | no |
| `client_secret_*.json` | Your Google OAuth client. Treat it like a password. | no |

To revoke the tool's access, remove the app at
[myaccount.google.com/permissions](https://myaccount.google.com/permissions).
