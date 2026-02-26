import os
import shutil
from PIL import Image
from time import sleep, time
import re
import requests
import json

def getMyGamesAndNames(source: str) -> tuple[dict[str, str], dict[str, str]]:
    games_by_name : dict[str, str] = {} # map name to appID
    games_by_appID : dict[str, str] = {} # map appID to name

    appid_pattern = r'^\s*"appid"[^"]*"(\d*)"(?:.|\n)*"name"[^"]*"([^"]*)"'
    print("Scanning, please wait...")
    for root, dirsnames, filesnames in os.walk(source):
        for file in filesnames:
            if file.startswith('appmanifest_') and file.endswith('.acf'):
                with open(os.path.join(root, file), "r") as F:
                    manifest = F.read()
                    match = re.search(appid_pattern, manifest, re.MULTILINE | re.IGNORECASE)
                    if not match:
                        print("No match in file " + file)
                    else:
                        appid, name = match.groups()[0], match.groups()[1]
                        games_by_name[name] = appid
                        games_by_appID[appid] = name
    print("Scan Complete")
    return (games_by_appID, games_by_name)

def getImages(platform: str, source: str, cachefolder: str = "dummy"):

    games_by_appID, games_by_name = getMyGamesAndNames(source)
    print('Acquired real games list')

    platform = platform.lower().strip()
    gogpath = 'C:\\ProgramData\\GOG.com\\Galaxy'
    steampath = 'C:\\Program Files (x86)\\Steam'
    
    # clear and rebuild the image cache
    dest_path = os.path.join(os.getcwd(), cachefolder)
    if cachefolder != '' and cachefolder in os.listdir():
        shutil.rmtree(os.path.join(dest_path)) # careful you could delete the whole project if cachefolder is empty
    os.mkdir(cachefolder)

    if platform == 'steam':
        steampath = os.path.join(steampath, 'appcache\\librarycache')
        for root, dirs, files in os.walk(steampath):
            for file in files:
                if file.endswith('.jpg'):
                    with Image.open(os.path.join(root, file)) as im:
                        if im.size == (32, 32) or file.endswith('600x900.jpg') or file.endswith('_capsule.jpg'):
                            appIDcandidates = [root.split("\\")[-1], root.split("\\")[-2], root.split("\\")[-3]]
                            for appID in appIDcandidates:
                                if appID in games_by_appID:
                                    shutil.copy(os.path.join(root, file), dest_path)
                                    if im.size == (32, 32):
                                        shutil.move(os.path.join(dest_path, file), os.path.join(dest_path, (games_by_appID[appID][:5] + '_' + appID + '_icon.jpg')))
                                        print(f"copied {file} to {dest_path}\\{games_by_appID[appID] + '_' + appID + '_icon.jpg'}")
                                    else:
                                        shutil.move(os.path.join(dest_path, file), os.path.join(dest_path, (games_by_appID[appID][:5] + '_' + appID + '_lib.jpg')))
                                        print(f"copied {file} to {dest_path}\\{games_by_appID[appID] + '_' + appID + '_lib.jpg'}")
                                elif appID.isdecimal() and not appID in games_by_appID:
                                    print("Game found, but it's not installed: " + appID + " (could be cached from the store)")
                    
    
    elif platform == 'gog':
        gogpath += '\\webcache'
        # res = (342, 482)
        # todo: implement gog support

def isSteamGameVR(appID: str) -> bool:
    # max call speed: rate limit 100k/d is ~ every 864 ms
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

def buildGameList(source: str):
    games_by_appID, games_by_name = getMyGamesAndNames(source)
    
    with open('batch_game_list.h', 'wt') as F:
        F.write('#pragma once\n')
        F.write('#include <Arduino.h>\n')
        F.write('static const char *P_game_list[] PROGMEM = {\n')
        
        time_of_last_request = 0
        for appID in games_by_appID:
            g = ''.join(c for c in games_by_appID[appID] if c.isalnum())
            # filter out soundtracks, demos 
            if ' soundtrack' in g.lower() or ' demo' in g.lower():
                print('Skipping ' + g + ' because it is a soundtrack or demo game')
                continue
            
            # rate limit
            # rate_limit = 0.864
            rate_limit = 0
            while time() - time_of_last_request < rate_limit:
                pass # wait
            time_of_last_request = time()
            vr = "Y" if isSteamGameVR(appID=appID) else "N"
            F.write(f'\t"{g}:{appID}:{vr}",\n')
        
        F.write('\t"\\0"\n')
        F.write('};\n')
    print('Build games list: complete')

def main():

    #getImages('steam', 'G:\\Games\\Steam\\steamapps', 'images')
    #buildGameList('G:\\Games\\Steam\\steamapps')
    buildGameList('C:\\Program Files (x86)\\Steam\\steamapps')

if __name__ == '__main__':
    main()
