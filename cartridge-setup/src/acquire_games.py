import os
import shutil
from datetime import datetime
from math import floor, ceil
from time import time, strftime, sleep
from random import random
import re
import requests
import numpy as np
import cv2  # opencv-python
import img2pdf

ListFileMaxNameBytes = 16
ImageCacheDir = "copied_images_cache"
GameListPrefix = "batch_game_list_local_"
LegacyGameListFile = "batch_game_list_local.txt"
LegacyGameListBackup = "batch_game_list_local.bak"


def createTimestampedGameListPath(directory: str = ".", now: datetime | None = None) -> str:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    candidate = os.path.join(directory, f"{GameListPrefix}{timestamp}.txt")
    suffix = 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{GameListPrefix}{timestamp}_{suffix}.txt")
        suffix += 1
    return candidate


def getLatestGameListPath(directory: str = ".") -> str | None:
    timestamp_pattern = re.compile(rf"^{re.escape(GameListPrefix)}(\d{{8}}_\d{{6}})(?:_(\d+))?\.txt$")
    timestamped_files: list[tuple[datetime, int, str]] = []
    for filename in os.listdir(directory):
        match = timestamp_pattern.match(filename)
        if match:
            try:
                timestamp = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")
            except ValueError:
                print(f"Ignoring game-list file with invalid timestamp: {filename}")
                continue
            sequence = int(match.group(2) or 0)
            timestamped_files.append((timestamp, sequence, os.path.join(directory, filename)))
    if timestamped_files:
        return max(timestamped_files, key=lambda item: (item[0], item[1]))[2]

    for legacy_name in (LegacyGameListFile, LegacyGameListBackup):
        legacy_path = os.path.join(directory, legacy_name)
        if os.path.isfile(legacy_path):
            return legacy_path
    return None


def getMyGamesAndNames(source: str) -> dict[str, str]:
    # return a dictionary mapping appIDs to names, stripping any special characters
    games_by_appID: dict[str, str] = {}  # map appID to name

    appid_pattern = r'^\s*"appid"[^"]*"(\d*)"(?:.|\n)*"name"[^"]*"([^"]*)"'

    print("Scanning, please wait...")
    source += "/steamapps"
    files_and_dirs = os.listdir(source)
    for file in files_and_dirs:  # could be a dir
        if file.startswith("appmanifest_") and file.endswith(".acf"):  # having this extension all but guarantees its a file
            # print(f'Reading {file}...')
            with open(os.path.join(source, file), "r") as F:
                manifest = F.read()
                match = re.search(appid_pattern, manifest, re.MULTILINE | re.IGNORECASE)
                if not match:
                    print("No match in file " + file)
                else:
                    appid, name = match.groups()[0], match.groups()[1]
                    games_by_appID[appid] = name

    print("Scan Complete")
    return games_by_appID


def removeMiscGames(all_games: dict) -> dict:
    filter_out_substrings = (
        "SteamLinuxRuntime",
        "ProtonExperimental",
        "Proton90",
        "tModLoader",
        "3DMark",
        "Natural Locomotion",
        "Wallpaper Engine",
        "Friend's Pass",
    )
    filter_out_words = re.compile(r"(?<!\w)(?:soundtrack|demo)(?!\w)", re.IGNORECASE)
    skipped_games = []
    for game_id, game_name in list(all_games.items()):
        normalized_name = re.sub(r"\s+", " ", game_name).replace("’", "'").casefold()
        if filter_out_words.search(game_name) or any(name.casefold() in normalized_name for name in filter_out_substrings):
            skipped_games.append(game_name)
            all_games.pop(game_id)
    if len(skipped_games) > 0:
        print(f"Skipping these: {skipped_games}")
    return all_games


def asciiify(all_games: dict) -> dict:
    # remove non ascii and then non alnum chars
    # not ascii encoding first has led to some chars like (R) slipping through
    for gameID in list(all_games):
        name = all_games[gameID]
        name = name.encode("ascii", errors="ignore").decode("utf-8", errors="ignore")
        name = "".join(c for c in name if c.isalnum())
        all_games.pop(gameID)
        all_games[gameID] = name

    return all_games


def getImages(platform: str, source: str, games_by_appID: dict[str, str], cachefolder: str):
    def flatten_list(xss):
        return [x for xs in xss for x in xs]

    if not cachefolder:
        return

    platform = platform.lower().strip()

    # clear and rebuild the image cache
    dest_path = os.path.join(os.getcwd(), cachefolder)
    if os.path.isdir(dest_path):
        shutil.rmtree(dest_path)
    os.mkdir(dest_path)

    if platform == "steam":
        source = os.path.join(source, "appcache/librarycache")
        partials = set()
        for root, dirs, files in os.walk(source):
            for file in files:
                if file.endswith(".jpg"):
                    im = cv2.imread(os.path.join(root, file))
                    assert im is not None
                    im_h, im_w = im.shape[:2]
                    if (im_h, im_w) == (32, 32) or file.endswith("600x900.jpg") or file.endswith("_capsule.jpg"):
                        # when we find an image, we don't know what search depth is at
                        appIDcandidates = flatten_list([d.split("/") for d in root.split("\\")])
                        for appID in appIDcandidates:
                            if appID in games_by_appID:
                                shutil.copy(os.path.join(root, file), dest_path)
                                if (im_h, im_w) == (32, 32):
                                    shutil.move(os.path.join(dest_path, file), os.path.join(dest_path, (games_by_appID[appID][:5] + "_" + appID + "_icon.jpg")))
                                else:
                                    shutil.move(os.path.join(dest_path, file), os.path.join(dest_path, (games_by_appID[appID][:5] + "_" + appID + "_lib.jpg")))
                            elif appID.isdecimal() and not appID in games_by_appID:
                                if not (appID in partials):
                                    partials.add(appID)
        if len(partials) > 0:
            print(f"{len(partials)} partial games found and skipped (they are not installed, and they could be cached data from the store)")

    elif platform == "gog":
        pass
        # todo: implement gog support
        # gogpath = 'C:\\ProgramData\\GOG.com\\Galaxy'
        # gogpath += '\\webcache'
        # res = (342, 482)


def generatePrintableImageGrids(source: str, width: int = floor(300 * 8.5), height: int = floor(300 * 11)) -> int:
    # default w x h is us-letter
    # made specifically for a 6x7 grid of 300x450 images with icons
    def drawGrid(bg, images, rows, cols, start_x=0, start_y=0, pad_x=0, pad_y=0, rotation=0):
        assert rotation in (0, 90, 180, 270)
        rot_map = {0: None, 90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}

        out = bg.copy()
        sample = images[0]

        if rotation != 0:
            sample = cv2.rotate(sample, rot_map[rotation])
        h, w = sample.shape[:2]

        for idx, img in enumerate(images):
            r = idx // cols
            c = idx % cols
            if r >= rows:
                break

            tile = img.copy()
            if rotation != 0:
                tile = cv2.rotate(tile, rot_map[rotation])

            x = start_x + c * (w + pad_x)
            y = start_y + r * (h + pad_y)
            out[y : y + h, x : x + w] = tile

        return out

    page = 0
    paths_lib = sorted([os.path.join(source, iname) for iname in os.listdir(source) if "_lib.jpg" in iname])
    # build icons indirectly from library to avoid duplicates/mismatches
    paths_ico = sorted([os.path.join(source, iname.replace("_lib", "_icon")) for iname in os.listdir(source) if "_lib.jpg" in iname])
    background = np.ones((height, width, 3), dtype=np.uint8) * 255  # basic, all white
    max_pages: int = ceil(len(paths_lib) / 42)

    while True:
        # collect a set of images
        if page == max_pages:  # todo: break when actual limit reached
            break
        print(f"Organizing page {page+1} of {max_pages}")

        path_set = paths_lib[(page * 42) : (page * 42 + 42)]
        # get library cards, scale if necessary
        tiles = [cv2.resize(cv2.imread(p), (300, 450), interpolation=cv2.INTER_NEAREST) for p in path_set]  # type: ignore
        result = drawGrid(bg=background, images=tiles, rows=7, cols=6, start_x=137, start_y=72, pad_x=70, pad_y=2, rotation=0)

        # create bridges, a 4x64 strip on the left side to cover the gap between the icon
        tiles = [cv2.GaussianBlur(t[23 : (23 + 64), :4], (3, 3), sigmaX=0, borderType=cv2.BORDER_WRAP) for t in tiles]
        result = drawGrid(bg=result, images=tiles, rows=7, cols=6, start_x=133, start_y=95, pad_x=366, pad_y=388, rotation=0)

        path_set = paths_ico[(page * 42) : (page * 42 + 42)]
        # get icons and scale them
        tiles = [cv2.resize(cv2.imread(p), (64, 64), interpolation=cv2.INTER_NEAREST) for p in path_set]  # type: ignore
        result = drawGrid(bg=result, images=tiles, rows=7, cols=6, start_x=69, start_y=95, pad_x=306, pad_y=388, rotation=90)

        cv2.imwrite(f"{source}/sheet_p{page+1}.png", result)
        page += 1

    # convert generated images cache to pdf
    print("Generating .PDF")
    with open("printer_sheets.pdf", "wb") as F:
        pngs = sorted(
            [f"{source}/{i}" for i in os.listdir(source) if i.endswith(".png") and i.startswith("sheet_p")],
            key=lambda fname: int(fname.rsplit(".", 1)[0].split("sheet_p")[1]),
        )
        pdfbytes = img2pdf.convert(pngs)
        assert pdfbytes is not None
        F.write(pdfbytes)

    return max_pages


def isSteamGameVR(appID: str) -> bool:
    # max call speed: rate limit is 200 calls per 5min (every 667 ms) or 100k/d (every 864 ms) whichever is hit first
    # don't call in automated tests
    response = requests.get(f"https://store.steampowered.com/api/appdetails?appids={appID}")
    if response.status_code != 200:
        raise Exception

    if response.json()[appID]["success"]:
        data = response.json()[appID]["data"]
        if "categories" in data:
            cats = response.json()[appID]["data"]["categories"]
            for i in cats:
                if i["id"] in [53, 54]:  # code for "VR supported", "VR only"
                    return True
        else:
            print(f"App {data['name']} ({appID}) has no category/feature tags (probably a soundtrack), ignoring VR options.")
    return False


def buildGameList(ofile: str, games_by_appID: dict[str, str], doRequests: bool = False):

    appIDListLimit = 255  # list limit for the random games section, not a hard library size limit
    rate_limit = 0.001
    if doRequests:
        rate_limit = 0.668
        print("Writing game list, this may take a moment...")
    else:
        print("Writing game list")

    with open(ofile, "wt") as F:
        F.write(f'<> Game list automatically generated on {strftime("%D %T %p")}\n')

        time_of_last_request = 0
        counter = 0
        vr_counter = 0
        vr_app_ids: set[str] = set()
        for appID in games_by_appID:
            counter = counter + 1
            print(f"\r({counter}/{len(games_by_appID)})", end="")

            gameName = games_by_appID[appID]

            # rate limit
            time_until_next_request = rate_limit - (time() - time_of_last_request)
            if time_until_next_request > 0:
                sleep(time_until_next_request)
            time_of_last_request = time()
            vr = "N"
            if doRequests:
                if isSteamGameVR(appID=appID):
                    vr = "Y"
                    vr_counter += 1
                    vr_app_ids.add(appID)
            F.write(f"{gameName}:{appID}:{vr}\n")

        print()

        # write non-vr games to the random eeprom
        F.write("<> Random games\n")
        for i, appID in enumerate(sorted(list(games_by_appID), key=lambda _: random())):
            if i >= appIDListLimit:
                break
            if appID in vr_app_ids:
                print(f"Skipped writing {games_by_appID[appID]} to random games list")
                appIDListLimit += 1  # try for a different game
                continue
            F.write(f"{appID}\n")

    print(f"Exported {counter} games, {vr_counter} tagged as using VR")


def getGamesFromFile(infile: str) -> dict[str, str]:
    lines: str = ""
    games_file_pattern = r"""^([^<\s]\S*):(\d+):"""
    games_from_file_by_appid = {}

    with open(infile, "rt") as F:
        lines = F.read()

    matches = re.findall(games_file_pattern, lines, re.MULTILINE)
    for match in matches:
        nameTruncated, appid = match[0], match[1]
        games_from_file_by_appid[appid] = nameTruncated
    return games_from_file_by_appid


def deleteImagesCache(dir: str = ImageCacheDir) -> None:
    if os.path.exists(dir):
        shutil.rmtree(dir)
