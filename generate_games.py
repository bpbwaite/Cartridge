import os
import shutil
from math import floor, ceil
from time import time, sleep
from random import random
import re
import requests
import numpy as np
import cv2 # opencv-python

# todo: unify function naming convention to camelCase, invent clever variable names

def getMyGamesAndNames(source: str) -> dict[str, str]:
    # return a dictionary mapping appIDs to names, stripping any special characters
    games_by_appID : dict[str, str] = {} # map appID to name

    appid_pattern = r'^\s*"appid"[^"]*"(\d*)"(?:.|\n)*"name"[^"]*"([^"]*)"'
    
    print("Scanning, please wait...")
    source += '/steamapps'
    files_and_dirs = os.listdir(source)
    for file in files_and_dirs: # could be a dir
        if file.startswith('appmanifest_') and file.endswith('.acf'): # having this extension all but guarantees its a file
            #print(f'Reading {file}...')
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

def no_misc_games(all_games: dict) -> dict:
    # filter out soundtracks, demos
    filter_out = {'SteamLinuxRuntime', 'Soundtrack', ' Demo', 'ProtonExperimental', 'Proton90', 'tModLoader'}
    skipped_games = []
    for gameID in list(all_games):
        gameName = all_games[gameID]
        for filt in filter_out:
            if filt in gameName:
                skipped_games.append(gameName)
                all_games.pop(gameID)
    if len(skipped_games) > 0:
        print(f'Skipping these: {skipped_games}')
    return all_games

def make_ascii_compatible(all_games: dict) -> dict:
    # remove non ascii and then non alnum chars
    # not ascii encoding first has led to some chars like (R) slipping through
    for gameID in list(all_games):
        name = all_games[gameID]
        name = name.encode("ascii", errors='ignore').decode("utf-8", errors='ignore')
        name = ''.join(c for c in name if c.isalpha())
        all_games.pop(gameID)
        all_games[gameID] = name
    
    return all_games

def getImages(platform: str, source: str, games_by_appID: dict[str, str] = {}, cachefolder: str = "dummy"):
    def flatten_list(xss):
        return [x for xs in xss for x in xs]
    
    platform = platform.lower().strip()
    #gogpath = 'C:\\ProgramData\\GOG.com\\Galaxy'
    
    # clear and rebuild the image cache
    dest_path = os.path.join(os.getcwd(), cachefolder)
    if cachefolder != '' and cachefolder in os.listdir():
        shutil.rmtree(os.path.join(dest_path)) # careful you could delete the whole project if cachefolder is empty
    os.mkdir(cachefolder)

    if platform == 'steam':
        source = os.path.join(source, 'appcache/librarycache')
        partials = set()
        for root, dirs, files in os.walk(source):
            for file in files:
                if file.endswith('.jpg'):
                    im = cv2.imread(os.path.join(root, file))
                    assert im is not None
                    im_h, im_w = im.shape[:2]
                    if (im_h, im_w) == (32, 32) or file.endswith('600x900.jpg') or file.endswith('_capsule.jpg'):
                        # when we find an image, we don't know what search depth is at
                        appIDcandidates = flatten_list([d.split("/") for d in root.split("\\")])
                        for appID in appIDcandidates:
                            if appID in games_by_appID:
                                shutil.copy(os.path.join(root, file), dest_path)
                                if (im_h, im_w) == (32, 32):
                                    shutil.move(os.path.join(dest_path, file), os.path.join(dest_path, (games_by_appID[appID][:5] + '_' + appID + '_icon.jpg')))
                                else:
                                    shutil.move(os.path.join(dest_path, file), os.path.join(dest_path, (games_by_appID[appID][:5] + '_' + appID + '_lib.jpg')))
                            elif appID.isdecimal() and not appID in games_by_appID:
                                if not (appID in partials):
                                    partials.add(appID)
        if len(partials) > 0:
            print(f"{len(partials)} partial games found and skipped (they are not installed, and they could be cached data from the store)")
                    
    
    elif platform == 'gog':
        pass
        #gogpath += '\\webcache'
        # res = (342, 482)
        # todo: implement gog support

def draw_grid_on_background(bg, images, rows, cols, start_x=0, start_y=0, pad_x=0, pad_y=0, rotation=0):
    assert rotation in (0, 90, 180, 270)

    rot_map = {
        0: None,
        90: cv2.ROTATE_90_CLOCKWISE,
        180: cv2.ROTATE_180,
        270: cv2.ROTATE_90_COUNTERCLOCKWISE
    }

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

        out[y:y+h, x:x+w] = tile

    return out

def generatePrintableImageGrids(source: str) -> None:
    width = floor(300*8.5) # us-letter
    height = floor(300*11) # us-letter
    page = 0
    paths_lib = sorted([os.path.join(source, iname) for iname in os.listdir(source) if '_lib.jpg' in iname])
    # build icons indirectly from library to avoid duplicates/mismatches
    paths_ico = sorted([os.path.join(source, iname.replace('_lib', '_icon')) for iname in os.listdir(source) if '_lib.jpg' in iname])
    background = np.ones((height, width, 3), dtype=np.uint8) * 255 # basic, all white 
    max_pages: int = ceil(len(paths_lib) / 42)
    
    while(True):
        # collect a set of images
        if page == max_pages: # todo: break when actual limit reached
            break
        print(f'Creating sheet {page+1} of {max_pages}')

        path_set = paths_lib[(page*42) : (page*42+42)]
        # get library cards, scale if necessary
        tiles = [cv2.resize(cv2.imread(p), (300, 450), interpolation=cv2.INTER_NEAREST) for p in path_set] # type: ignore
        # do multiple times per group
        result = draw_grid_on_background(
            bg=background,
            images=tiles,
            rows=7,
            cols=6,
            start_x=137,
            start_y=72,
            pad_x=70,
            pad_y=2,
            rotation=0
        )

        path_set = paths_ico[(page*42) : (page*42+42)]
        # get icons and scale them 
        tiles = [cv2.resize(cv2.imread(p), (64, 64), interpolation=cv2.INTER_NEAREST) for p in path_set] # type: ignore
        result = draw_grid_on_background(
            bg=result,
            images=tiles,
            rows=7,
            cols=6,
            start_x=69,
            start_y=95,
            pad_x=306,
            pad_y=388,
            rotation=90
        )

        cv2.imwrite(f"sheet_p{page+1}.png", result)
        page += 1

def isSteamGameVR(appID: str) -> bool:
    # max call speed: rate limit is 200 calls per 5min (every 667 ms) or 100k/d (every 864 ms) whichever is hit first
    response = requests.get(f'https://store.steampowered.com/api/appdetails?appids={appID}')
    if response.status_code != 200:
        raise Exception
    
    if response.json()[appID]['success']:
        data = response.json()[appID]['data']
        if 'categories' in data:
            cats = response.json()[appID]['data']['categories']
            for i in cats:
                if i['id'] in [53, 54]: # code for "VR supported", "VR only"
                    return True
        else:
            print(f"App {data['name']} ({appID}) has no category/feature tags (probably a soundtrack), ignoring VR options.")
    return False

def buildGameList(games_by_appID: dict[str, str], doRequests: bool = False):
    
    appIDListLimit = 128 # list limit for the random games section, not a hard library size limit
    rate_limit = 0.01
    if doRequests:
        rate_limit = 0.668
        print('Writing header file, this may take a moment...')
    else:
        print('Writing header file')

    with open('batch_game_list.h', 'wt') as F:
        F.write('#ifndef BATCH_GAME_LIST_H\n')
        F.write('#define BATCH_GAME_LIST_H\n\n')
        F.write('#include <Arduino.h>\n\n')
        
        F.write('static const char * const P_game_list[] PROGMEM = {\n')
        time_of_last_request = 0
        counter = 0
        vr_counter = 0
        for appID in games_by_appID:
            counter = counter + 1
            print(f'\r({counter}/{len(games_by_appID)})', end="")
            
            gameName = games_by_appID[appID]
            
            # rate limit
            while time() - time_of_last_request < rate_limit:
                pass
            time_of_last_request = time()
            vr = "N"
            if doRequests:
                if isSteamGameVR(appID=appID):
                    vr = "Y"
                    vr_counter += 1
                    games_by_appID[appID] += '_VR=TRUE' # reuse this dictionary, could be dangerous, we'll see
            F.write(f'\t"{gameName}:{appID}:{vr}",\n')

        print()
        F.write('\t"\\0"\n')
        F.write('};\n')

        # write non-vr games to the random eeprom
        F.write('static const uint32_t PROGMEM P_appID_list[] = {\n')
        for i, appID in enumerate(sorted(list(games_by_appID), key=lambda _: random())):
            if i >= appIDListLimit:
                break
            if '_VR=TRUE' in games_by_appID[appID]:
                print(f'Skipped writing {games_by_appID[appID]} to random games list')
                appIDListLimit += 1 # try for a different game
                continue
            F.write(f'{appID}, ')
        F.write('\n};\n\n')
        F.write('#endif\n')

    print(f'Build games list: complete. ({counter} games, {vr_counter} tagged as using VR)')

def main():
    steam_install_path = 'C:/Program Files (x86)/Steam'
    steam_library_path = 'G:/Games/Steam'
    need_VR_tags = False
    
    games_by_appID = make_ascii_compatible(no_misc_games(getMyGamesAndNames(steam_library_path)))
    print('Acquired real installed games list')
    
    getImages('steam', steam_install_path, games_by_appID, './generated_images')
    generatePrintableImageGrids('./generated_images')
    buildGameList(games_by_appID, doRequests=need_VR_tags)

if __name__ == '__main__':
    main()
