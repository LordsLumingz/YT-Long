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


def list_videos(yt, pattern, any_visibility, deep):
    uploads = yt.channels().list(part="contentDetails", mine=True).execute()
    uploads = uploads["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    ids, token = [], None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=uploads,
                                    maxResults=50, pageToken=token).execute()
        ids += [i["contentDetails"]["videoId"] for i in r["items"]]
        token = r.get("nextPageToken")
        if not token:
            break

    if deep:  # drafts sometimes miss the uploads playlist; search costs 100 units/page
        token = None
        for _ in range(3):
            r = yt.search().list(part="id", forMine=True, type="video",
                                 maxResults=50, pageToken=token).execute()
            ids += [i["id"]["videoId"] for i in r["items"]]
            token = r.get("nextPageToken")
            if not token:
                break
    ids = list(dict.fromkeys(ids))

    videos = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet,status,fileDetails", id=",".join(ids[i:i + 50])).execute()
        videos += r["items"]

    keep = []
    for v in videos:
        name = v.get("fileDetails", {}).get("fileName", "")
        if not name or not re.search(pattern, name):
            continue
        if not any_visibility and v["status"]["privacyStatus"] != "private":
            continue
        keep.append(v)
    keep.sort(key=lambda v: natural(v["fileDetails"]["fileName"]))
    return keep


def cmd_export(args):
    yt = get_service()
    videos = list_videos(yt, args.pattern, args.any_visibility, args.deep)
    old = {}
    if TITLES.exists():
        with TITLES.open(encoding="utf-8-sig", newline="") as f:
            old = {r["video_id"]: r["title"] for r in csv.DictReader(f)}
    with TITLES.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["video_id", "filename", "current_title", "title"])
        for v in videos:
            w.writerow([v["id"], v["fileDetails"]["fileName"], v["snippet"]["title"], old.get(v["id"], "")])
    print(f"{len(videos)} videos -> {TITLES}")
    print("Fill in the 'title' column (blank = '<prefix> #N'), save, then run apply.")


def cmd_apply(args):
    if not TITLES.exists():
        sys.exit("titles.csv missing, run 'export' first")
    with TITLES.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    done = json.loads(DONE.read_text()) if DONE.exists() else {}

    yt = get_service()
    current = {v["id"]: v for v in list_videos(yt, args.pattern, args.any_visibility, args.deep)}

    plan, counter = [], 0
    for r in rows:
        title = r["title"].strip()
        if not title and not untitled(r["filename"], r["current_title"]):
            print(f"skip (already has its own title, leave 'title' blank to keep): {r['filename']}")
            continue
        if not title:
            counter += 1
            title = f"{args.prefix} #{counter}"
        stem = Path(r["filename"]).stem
        desc = f"{stem}\n{args.line}" if args.line else stem
        if len(title) > 100:
            sys.exit(f"title too long (>100): {title}")
        plan.append((r["video_id"], r["filename"], title, desc))

    def finished(vid):
        d = done.get(vid)
        return bool(d) and (not args.visibility or d.get("visibility") == args.visibility)

    todo = [p for p in plan if not finished(p[0]) and p[0] in current]
    missing = [p[1] for p in plan if p[0] not in current and p[0] not in done]
    if missing:
        print(f"not found on channel (skipped): {', '.join(missing)}")
    if args.limit:
        todo = todo[:args.limit]

    for vid, fname, title, desc in todo:
        print(f"{fname:<20} -> {title!r} | {desc!r}")
    print(f"\n{len(todo)} to update, {len(done)} already done.")
    if args.dry_run or not todo:
        return

    for vid, fname, title, desc in todo:
        sn = current[vid]["snippet"]
        body = {"id": vid, "snippet": {
            "title": title,
            "description": desc,
            "categoryId": sn.get("categoryId", FALLBACK_CATEGORY),
        }}
        for k in ("tags", "defaultLanguage"):
            if k in sn:
                body["snippet"][k] = sn[k]
        part = "snippet"
        if args.visibility:
            # videos.update replaces the whole status part, so start from the existing one
            st = current[vid]["status"]
            new = {k: st[k] for k in ("embeddable", "license", "publicStatsViewable") if k in st}
            new["privacyStatus"] = args.visibility
            if args.not_for_kids:
                new["selfDeclaredMadeForKids"] = False
            elif "selfDeclaredMadeForKids" in st:
                new["selfDeclaredMadeForKids"] = st["selfDeclaredMadeForKids"]
            body["status"] = new
            part = "snippet,status"
        try:
            yt.videos().update(part=part, body=body).execute()
        except HttpError as e:
            if "quotaExceeded" in str(e):
                print("Daily quota used up. Run again tomorrow, finished videos are skipped.")
                break
            print(f"FAILED {fname}: {e}")
            continue
        done[vid] = {"title": title, "visibility": args.visibility}
        DONE.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"ok  {fname}")


HELP = f"""\
YT-Long {__version__} (yt_batch.py)
Batch-set titles, descriptions and visibility on your YouTube videos.

USAGE
  python yt_batch.py <command> [options]

COMMANDS
  export    List your private videos and write titles.csv. Fill in its
            'title' column; rows left blank become '<prefix> #N'. Titles you
            already typed are kept when you run export again.
  apply     Read titles.csv and update each video: title from the CSV,
            description = original filename, plus --line on a second line.
            Videos already done are skipped, so rerunning is safe.
  help, ?   Show this screen (also: no command, -h, --help).
  version   Print the version (also: -V, --version).

OPTIONS (export / apply)
  --line TEXT         Text added to every description, under the filename
                      [default: none]
  --prefix TEXT       Title prefix for rows left blank       [default: Video]
  --pattern REGEX     Only videos whose original filename matches. "^IMG_"
                      means: filename starts with IMG_       [default: all]
  --any-visibility    Include videos that are not private
  --deep              Also search for drafts missing from the uploads list
                      (costs more API quota)

OPTIONS (apply only)
  --dry-run           Print what would change, change nothing
  --limit N           Only update the first N videos (use 1 to test)
  --visibility V      Also set visibility: public | unlisted | private
  --not-for-kids      Declare the videos NOT made for kids (needed to publish
                      a draft; this is your declaration, not a default)

EXAMPLES
  python yt_batch.py export --pattern "^IMG_"
  python yt_batch.py apply --pattern "^IMG_" --line "Shot on my phone" --dry-run
  python yt_batch.py apply --pattern "^IMG_" --line "Shot on my phone" --limit 1
  python yt_batch.py apply --pattern "^IMG_" --visibility public --not-for-kids

FILES (in this folder)
  titles.csv   your titles        done.json   log of finished videos
  token.json   your login (keep private)
"""


def main():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("command", nargs="?", default="help", choices=["export", "apply", "help", "?", "version"])
    p.add_argument("-h", "--help", dest="show_help", action="store_true")
    p.add_argument("-V", "--version", dest="show_version", action="store_true")
    p.add_argument("--line", default="", help="shared description line")
    p.add_argument("--prefix", default="Video", help="fallback title prefix")
    p.add_argument("--pattern", default="", help="regex on original filename")
    p.add_argument("--any-visibility", action="store_true", help="include non-private videos")
    p.add_argument("--deep", action="store_true", help="also search for drafts missing from uploads list")
    p.add_argument("--visibility", choices=["public", "unlisted", "private"],
                   help="also set visibility (default: leave as is)")
    p.add_argument("--not-for-kids", action="store_true",
                   help="declare the videos NOT made for kids (needed to publish a draft)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()
    if args.show_version or args.command == "version":
        print(f"YT-Long {__version__}")
        return
    if args.show_help or args.command in ("help", "?"):
        print(HELP)
        return
    {"export": cmd_export, "apply": cmd_apply}[args.command](args)


if __name__ == "__main__":
    main()
