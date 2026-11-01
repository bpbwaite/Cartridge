# todo: invent even more clever variable names
# todo: use globs where appropriate
# todo: abstract out constants, protocols, formats...

import os
import shutil
from time import sleep

from acquire_games import (
    ImageCacheDir,
    ListFileMaxNameBytes,
    asciiify,
    buildGameList,
    deleteImagesCache,
    generatePrintableImageGrids,
    getGamesFromFile,
    getImages,
    getMyGamesAndNames,
    removeMiscGames,
)
from flash_games import writeGamesSerial


def main():
    # get installation path variables from user
    default_steampaths = "C:/Program Files (x86)/Steam"
    games_eeprom_file = "batch_game_list_local.txt"
    games_eeprom_file_old = "batch_game_list_local.bak"
    yes = {"y", "yes"}
    choiceIgnore = {"a", "ignore"}
    choiceDiff = {"b", "only"}
    choiceUpload = {"c", "skip"}

    # if there is an eeprom file, ask if we want to skip ahead and install it, or only run on the difference
    if os.path.isfile(games_eeprom_file):
        choice = (
            input(
                "There is an existing list. Would you like to (A) Ignore and start over, (B) Only build and upload new games since the last run, or (C) Skip build and upload games now? (A/B/C) >> "
            )
            .lower()
            .strip()
        )
        if choice in choiceUpload:
            writeGamesSerial(games_eeprom_file)
            return
        if choice in choiceDiff:
            shutil.copy(games_eeprom_file, games_eeprom_file_old)
        if choice in choiceIgnore:
            # default
            os.remove(games_eeprom_file)
            os.remove(games_eeprom_file_old)

    steam_install_path = input('Is Steam installed at "' + default_steampaths + '"? (y/n) >> ')
    if steam_install_path.lower() in yes:
        steam_install_path = default_steampaths
    else:
        steam_install_path = input("Enter the location of your Steam install, e.g. G:/Programs/Steam\n>> ")
    steam_library_path = input('Are your Steam games installed at "' + default_steampaths + '"? (y/n) >> ')
    if steam_library_path.lower() in yes:
        steam_library_path = default_steampaths
    else:
        steam_library_path = input("Enter the location of your Steam library, e.g. G:/Games/Steam\n>> ")
    need_VR_tags = False
    if input("Do you need tags for your VR titles? Advanced option, takes longer. (y/n) >> ").lower() in yes:
        need_VR_tags = True
    wants_eeprom = False
    if input("Would you like to upload the games list upon completion? (y/n) >> ").lower() in yes:
        wants_eeprom = True

    ###

    games_by_appID = asciiify(removeMiscGames(getMyGamesAndNames(steam_library_path)))
    # pre-write name truncation for possible comparison to .bak file, later
    for game in games_by_appID:
        games_by_appID[game] = games_by_appID[game][:ListFileMaxNameBytes]

    if os.path.exists(games_eeprom_file_old):
        games_by_appID_old = getGamesFromFile(games_eeprom_file_old)
        for app in games_by_appID_old:
            if app in games_by_appID:
                games_by_appID.pop(app)
        print("Acquired newly installed games list")
        # print('After writing over serial, rerun the program and choose (A) to properly setup random game functionality!')
        deleteImagesCache()
        getImages("steam", steam_install_path, games_by_appID, ImageCacheDir)
        n = generatePrintableImageGrids(ImageCacheDir)
        buildGameList(games_eeprom_file, games_by_appID, doRequests=need_VR_tags)
        print(f'You can now print the {n}-page "printer_sheets.pdf"')
        os.startfile("printer_sheets.pdf")

        # regenerate the whole list for flashing random and for next time
        games_by_appID_newest = asciiify(removeMiscGames(getMyGamesAndNames(steam_library_path)))
        for game in games_by_appID_newest:
            games_by_appID_newest[game] = games_by_appID_newest[game][:ListFileMaxNameBytes]
        buildGameList(games_eeprom_file, games_by_appID_newest, doRequests=need_VR_tags)

        if wants_eeprom:
            writeGamesSerial(games_eeprom_file, games_by_appID)

    else:
        print("Acquired real installed games list")
        getImages("steam", steam_install_path, games_by_appID, ImageCacheDir)
        n = generatePrintableImageGrids(ImageCacheDir)

        buildGameList(games_eeprom_file, games_by_appID, doRequests=need_VR_tags)

        print(f'You can now print the {n}-page "printer_sheets.pdf"')
        os.startfile("printer_sheets.pdf")

        if wants_eeprom:
            writeGamesSerial(games_eeprom_file)

    sleep(5)


if __name__ == "__main__":
    main()
