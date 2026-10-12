"""Batch-set titles and descriptions on videos already uploaded to YouTube.

  python yt_batch.py export                 # writes titles.csv (fill in the 'title' column)
  python yt_batch.py apply --dry-run        # preview, changes nothing
  python yt_batch.py apply --limit 1        # test on a single video
  python yt_batch.py apply                  # do all of them

Description = original filename without extension on line 1, then --line if given.
Title       = 'title' column from titles.csv, or '<prefix> #N' when left blank.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

__version__ = "0.2.5"

HERE = Path(__file__).resolve().parent
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
TOKEN = HERE / "token.json"
TITLES = HERE / "titles.csv"
DONE = HERE / "done.json"
PLAYLIST = HERE / "playlist.csv"
FALLBACK_CATEGORY = "19"  # Travel & Events, used only if a draft has no category yet

sys.stdout.reconfigure(encoding="utf-8")


def client_secret():
    for folder in (HERE, HERE.parent):
        found = sorted(folder.glob("client_secret*.json"))
        if found:
            return found[0]
    sys.exit("client_secret*.json not found in yt-batch/ or its parent folder")


def get_service():
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds and not creds.valid:
        try:
            if creds.refresh_token:
                creds.refresh(Request())
            else:
                creds = None
        except RefreshError:  # e.g. 7-day expiry while the app is in testing mode
            creds = None
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret()), SCOPES)
        creds = flow.run_local_server(port=0)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def natural(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def untitled(filename, current_title):
    """True while the title is still the one Studio derived from the filename
    (IMG_3976(1).MOV -> 'IMG 39761'), i.e. nobody has titled the video yet."""
    def norm(t):
        return re.sub(r"[\W_]+", "", t.lower())
    return norm(current_title) == norm(Path(filename).stem)


def fetch_videos(yt, ids):
    videos = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet,status,fileDetails", id=",".join(ids[i:i + 50])).execute()
        videos += r["items"]
    return videos


def list_videos(yt, pattern, any_visibility, deep, title_pattern="", untitled_only=False, in_playlist=""):
    if in_playlist:
        same = find_playlists(yt, in_playlist)
        if len(same) != 1:
            sys.exit(f"{len(same)} playlists are named {in_playlist!r}, run 'playlist' to see the names")
        source = same[0]["id"]
    else:
        source = yt.channels().list(part="contentDetails", mine=True).execute()
        source = source["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    ids, token = [], None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=source,
                                    maxResults=50, pageToken=token).execute()
        ids += [i["contentDetails"]["videoId"] for i in r["items"]]
        token = r.get("nextPageToken")
        if not token:
            break

    if deep and not in_playlist:  # drafts sometimes miss the uploads playlist; search costs 100 units/page
        token = None
        for _ in range(3):
            r = yt.search().list(part="id", forMine=True, type="video",
                                 maxResults=50, pageToken=token).execute()
            ids += [i["id"]["videoId"] for i in r["items"]]
            token = r.get("nextPageToken")
            if not token:
                break
    ids = list(dict.fromkeys(ids))

    keep = []
    for v in fetch_videos(yt, ids):
        name = v.get("fileDetails", {}).get("fileName", "")
        if not name or not re.search(pattern, name):
            continue
        if not any_visibility and v["status"]["privacyStatus"] != "private":
            continue
        if title_pattern and not re.search(title_pattern, v["snippet"]["title"]):
            continue
        if untitled_only and not untitled(name, v["snippet"]["title"]):
            continue
        keep.append(v)
    keep.sort(key=lambda v: natural(v["fileDetails"]["fileName"]))
    return keep


def cmd_export(args):
    yt = get_service()
    videos = list_videos(yt, args.pattern, args.any_visibility, args.deep,
                         args.title_pattern, args.untitled, args.in_playlist)
    old = {}
    if TITLES.exists():
        with TITLES.open(encoding="utf-8-sig", newline="") as f:
            old = {row_video_id(r): r["title"] for r in csv.DictReader(f)}
    with TITLES.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["video_id", "filename", "current_title", "title", "url"])
        for v in videos:
            w.writerow([v["id"], v["fileDetails"]["fileName"], v["snippet"]["title"], old.get(v["id"], ""),
                        f"https://youtu.be/{v['id']}"])
    print(f"{len(videos)} videos -> {TITLES}")
    print("Fill in the 'title' column (blank = '<prefix> #N'), save, then run apply.")


def get_playlists(yt):
    items, token = [], None
    while True:
        r = yt.playlists().list(part="snippet,status,contentDetails", mine=True,
                                maxResults=50, pageToken=token).execute()
        items += r["items"]
        token = r.get("nextPageToken")
        if not token:
            return items


def find_playlists(yt, name):
    return [p for p in get_playlists(yt) if p["snippet"]["title"].strip().lower() == name.strip().lower()]


def playlist_video_ids(yt, playlist_id):
    ids, token = set(), None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=playlist_id,
                                    maxResults=50, pageToken=token).execute()
        ids |= {i["contentDetails"]["videoId"] for i in r["items"]}
        token = r.get("nextPageToken")
        if not token:
            return ids


def cmd_playlist(args):
    items = sorted(get_playlists(get_service()), key=lambda p: natural(p["snippet"]["title"]))
    with PLAYLIST.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["playlist_title", "visibility", "videos", "playlist_id"])
        for p in items:
            w.writerow([p["snippet"]["title"], p["status"]["privacyStatus"],
                        p["contentDetails"]["itemCount"], p["id"]])
    print(f"{len(items)} playlists -> {PLAYLIST}")


def row_video_id(r):
    """Excel turns an id that starts with '-' or '=' into a formula (#NAME?), so
    fall back to the id inside the url column."""
    vid = (r.get("video_id") or "").strip().lstrip("='")
    if re.fullmatch(r"[\w-]{11}", vid):
        return vid
    m = re.search(r"youtu\.be/([\w-]{11})", r.get("url") or "")
    return m.group(1) if m else vid


def cmd_apply(args):
    """Each run changes only what it was asked to: a title typed in titles.csv,
    --line, --visibility, --not-for-kids, --playlist. Anything not asked for in
    this run is left as it is on YouTube, so the steps can be run one at a time
    and in any order."""
    if not TITLES.exists():
        sys.exit("titles.csv missing, run 'export' first")
    with TITLES.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    done = json.loads(DONE.read_text(encoding="utf-8")) if DONE.exists() else {}

    yt = get_service()
    # look the rows up by id: titles.csv decides what is touched, and the uploads
    # listing can lag behind (it has missed freshly published videos)
    current = {v["id"]: v for v in fetch_videos(yt, [row_video_id(r) for r in rows])}

    plan, missing, kept, counter = [], [], 0, 0
    for r in rows:
        vid, fname = row_video_id(r), r["filename"]
        if vid not in current:
            missing.append(fname)
            continue
        live, st = current[vid]["snippet"], current[vid]["status"]
        rec = done.get(vid) or {}
        managed = "title" in rec  # this tool has set the title before
        fresh = untitled(fname, live["title"])  # nobody has titled it yet
        stem = Path(fname).stem

        title = r["title"].strip()
        if not title and (managed or fresh):
            counter += 1
            if managed and args.prefix is None:
                title = rec["title"]
            else:
                title = f"{args.prefix or 'Video'} #{counter}"
        if len(title) > 100:
            sys.exit(f"title too long (>100): {title}")

        change = {}
        if title:
            if args.line is not None:
                desc = f"{stem}\n{args.line}" if args.line else stem
            elif managed or not fresh:
                # recorded value first: a read right after an update can be stale
                desc = rec.get("description", live.get("description", ""))
            else:
                desc = stem
            live_desc = live.get("description", "")
            logged = managed and rec["title"] == title and rec.get("description", live_desc) == desc
            same = live["title"] == title and live_desc == desc
            if args.force or not (logged or same):
                change["title"], change["description"] = title, desc
        else:
            kept += 1
        if args.visibility and (args.force or not (
                rec.get("visibility") == args.visibility or st["privacyStatus"] == args.visibility)):
            change["visibility"] = args.visibility
        if args.not_for_kids and (args.force or not (
                rec.get("kids") is False or st.get("selfDeclaredMadeForKids") is False)):
            change["kids"] = False
        plan.append((vid, fname, change))

    if missing:
        print(f"not found on YouTube (skipped): {', '.join(missing)}")
    todo = [p for p in plan if p[2]]
    if args.limit:
        todo = todo[:args.limit]
    for vid, fname, change in todo:
        print(f"{fname:<20} " + " | ".join(f"{k} -> {v!r}" for k, v in change.items()))
    if kept:
        print(f"{kept} rows have a blank 'title' and a video that is already titled: "
              "title and description left as they are.")
    print(f"{len(todo)} to update, {len(plan) - len([p for p in plan if p[2]])} need no change.")

    playlist_id, to_add = None, []
    if args.playlist:
        same = find_playlists(yt, args.playlist)
        if len(same) > 1:
            sys.exit(f"{len(same)} playlists are named {args.playlist!r}, rename one in Studio first")
        if same:
            playlist_id = same[0]["id"]
            already = playlist_video_ids(yt, playlist_id)
            print(f"playlist {same[0]['snippet']['title']!r} exists, {len(already)} videos in it")
        else:
            already = set()
            print(f"playlist {args.playlist!r} does not exist, it will be created ({args.playlist_visibility})")
        # every row of titles.csv goes in, including the ones whose title is kept
        to_add = [p for p in plan if p[0] not in already]
        if args.limit:
            to_add = to_add[:args.limit]
        print(f"{len(to_add)} to add to the playlist: {', '.join(p[1] for p in to_add) or '-'}")

    if args.dry_run or not (todo or to_add):
        return

    failed = set()
    for vid, fname, change in todo:
        sn, st = current[vid]["snippet"], current[vid]["status"]
        body, parts = {"id": vid}, []
        if "title" in change:
            # videos.update replaces a whole part, so carry over what is not changing
            body["snippet"] = {
                "title": change["title"],
                "description": change["description"],
                "categoryId": sn.get("categoryId", FALLBACK_CATEGORY),
            }
            for k in ("tags", "defaultLanguage"):
                if k in sn:
                    body["snippet"][k] = sn[k]
            parts.append("snippet")
        if "visibility" in change or "kids" in change:
            new = {k: st[k] for k in ("embeddable", "license", "publicStatsViewable", "selfDeclaredMadeForKids")
                   if k in st}
            new["privacyStatus"] = change.get("visibility", st["privacyStatus"])
            if "kids" in change:
                new["selfDeclaredMadeForKids"] = False
            body["status"] = new
            parts.append("status")
        try:
            yt.videos().update(part=",".join(parts), body=body).execute()
        except HttpError as e:
            if "quotaExceeded" in str(e):
                print("Daily quota used up. Run again tomorrow, finished videos are skipped.")
                return
            print(f"FAILED {fname}: {e}")
            failed.add(vid)
            continue
        done[vid] = {**done.get(vid, {}), **change}
        DONE.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"ok  {fname}")

    to_add = [p for p in to_add if p[0] not in failed]
    if not to_add:
        return
    try:
        if not playlist_id:
            playlist_id = yt.playlists().insert(part="snippet,status", body={
                "snippet": {"title": args.playlist},
                "status": {"privacyStatus": args.playlist_visibility},
            }).execute()["id"]
            print(f"created playlist {args.playlist!r}")
        for vid, fname, _ in to_add:  # appended in titles.csv order
            try:
                yt.playlistItems().insert(part="snippet", body={"snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": vid},
                }}).execute()
            except HttpError as e:
                if "quotaExceeded" in str(e):
                    raise
                print(f"FAILED to add {fname}: {e}")
                continue
            print(f"added  {fname}")
    except HttpError as e:
        if "quotaExceeded" not in str(e):
            raise
        print("Daily quota used up. Run again tomorrow, videos already in the playlist are skipped.")


HELP = f"""\
YT-Long {__version__} (yt_batch.py)
Batch-set titles, descriptions and visibility on your YouTube videos.

USAGE
  python yt_batch.py <command> [options]

COMMANDS
  export    List your private videos and write titles.csv. Fill in its
            'title' column; rows left blank become '<prefix> #N'. Titles you
            already typed are kept when you run export again.
  apply     Update the videos listed in titles.csv. Each run changes only
            what you ask for in that run (a typed title, --line, --visibility,
            --not-for-kids, --playlist) and leaves the rest as it is, so you
            can do the steps one at a time, in any order. Rerunning is safe.
  playlist  Write your playlists to playlist.csv: title, visibility, number
            of videos, id (also: getplaylist).
  help, ?   Show this screen (also: no command, -h, --help).
  version   Print the version (also: -V, --version).

OPTIONS (export only: which videos go into titles.csv)
  --pattern REGEX     Only videos whose original filename matches. "^IMG_"
                      means: filename starts with IMG_       [default: all]
                      In any REGEX: "a|b" = a OR b, "(?i)" in front = ignore
                      upper/lower case, e.g. "(?i)merbabu|lawu"
  --in-playlist NAME  Only videos that are in this playlist of yours
  --title-pattern REGEX
                      Only videos whose CURRENT YouTube title matches. Studio
                      turns IMG_3897.MOV into the title "IMG 3897", so use
                      "^IMG " (with a space), not "^IMG_"    [default: all]
  --untitled          Only videos nobody has titled yet (the title is still
                      the one made from the filename)
  --any-visibility    Include videos that are not private
  --deep              Also search for drafts missing from the uploads list
                      (costs more API quota)

OPTIONS (apply only: it updates exactly the rows in titles.csv)
  (no option)         Set titles typed in titles.csv. A video nobody has
                      titled yet also gets '<prefix> #N' if its row is blank,
                      and its filename as description.
  --line TEXT         Rewrite the description: filename, then TEXT under it
  --prefix TEXT       Title prefix for rows left blank       [default: Video]
  --dry-run           Print what would change, change nothing
  --force             Redo the changes even if they look already done
  --limit N           Only update the first N videos (use 1 to test)
  --visibility V      Also set visibility: public | unlisted | private
  --not-for-kids      Declare the videos NOT made for kids (needed to publish
                      a draft; this is your declaration, not a default)
  --playlist NAME     Also add the videos to this playlist, in titles.csv
                      order. Created if no playlist has that name. Videos
                      already in it are not added twice.
  --playlist-visibility V
                      Visibility of a newly created playlist: public |
                      unlisted | private                  [default: private]

EXAMPLES
  python yt_batch.py playlist
  python yt_batch.py apply --playlist "My trip" --dry-run
  python yt_batch.py export --pattern "^IMG_"
  python yt_batch.py apply --line "Shot on my phone" --dry-run
  python yt_batch.py apply --line "Shot on my phone" --limit 1
  python yt_batch.py apply --line "Shot on my phone" --visibility public --not-for-kids

FILES (in this folder)
  titles.csv   your titles        done.json   log of finished videos
  playlist.csv your playlists
  token.json   your login (keep private)
"""


def main():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("command", nargs="?", default="help", choices=["export", "apply", "playlist", "getplaylist", "help", "?", "version"])
    p.add_argument("-h", "--help", dest="show_help", action="store_true")
    p.add_argument("-V", "--version", dest="show_version", action="store_true")
    p.add_argument("--line", help="shared description line")
    p.add_argument("--prefix", help="fallback title prefix")
    p.add_argument("--force", action="store_true", help="redo changes even if they look already done")
    p.add_argument("--pattern", default="", help="regex on original filename")
    p.add_argument("--title-pattern", default="", help="regex on the current YouTube title")
    p.add_argument("--in-playlist", default="", help="only videos in this playlist")
    p.add_argument("--untitled", action="store_true", help="only videos still carrying their filename as title")
    p.add_argument("--any-visibility", action="store_true", help="include non-private videos")
    p.add_argument("--deep", action="store_true", help="also search for drafts missing from uploads list")
    p.add_argument("--visibility", choices=["public", "unlisted", "private"],
                   help="also set visibility (default: leave as is)")
    p.add_argument("--not-for-kids", action="store_true",
                   help="declare the videos NOT made for kids (needed to publish a draft)")
    p.add_argument("--playlist", help="also add the videos to this playlist (created if missing)")
    p.add_argument("--playlist-visibility", choices=["public", "unlisted", "private"], default="private",
                   help="visibility of a newly created playlist")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()
    if args.show_version or args.command == "version":
        print(f"YT-Long {__version__}")
        return
    if args.show_help or args.command in ("help", "?"):
        print(HELP)
        return
    {"export": cmd_export, "apply": cmd_apply,
     "playlist": cmd_playlist, "getplaylist": cmd_playlist}[args.command](args)


if __name__ == "__main__":
    main()
