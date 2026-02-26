#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>

#include <Adafruit_PN532.h>
#include <Adafruit_NeoPixel.h>

#include "batch_game_list.h"

#define PN532_SS               (10)
#define DEBUG_WAIT_FOR_SERIAL  (true)
#define SERIAL_BAUD            (115200) // PN532 likes this to be the case in some instances
#define NEOPIXEL_DATA          (2)
#define WIN_RUN_WAIT           (500)
#define BATCH_WRITE_MODE       (true)
#define NPXL_LEN               (1) // 1 or 3
#define CHIP_PEEK_POLLING_FREQ (5) // Hz, max 10 please

const char *CUSTOM_ASCII_DELIMITER = "\xBF"; // upside down question mark delimiter

// ### helper functions that can go in a header file. should not use globals, but defines ok
// PN532 functions
boolean init_pn532(Adafruit_PN532 *nfc, uint8_t limit_retries = 0xFF) {
    nfc->begin();
    uint32_t versiondata = nfc->getFirmwareVersion();
    if (!versiondata) {
        Serial.print("Didn't find PN53x board");
        return false;
    }
    Serial.print("Found chip PN5");
    Serial.println((versiondata >> 24) & 0xFF, HEX);
    Serial.print("Firmware ver. ");
    Serial.print((versiondata >> 16) & 0xFF, DEC);
    Serial.print('.');
    Serial.println((versiondata >> 8) & 0xFF, DEC);
    nfc->setPassiveActivationRetries(limit_retries);

    Serial.print("Using ");
    if (limit_retries == 0xFF) {
        Serial.print("infinite (blocking)");
    }
    else {
        Serial.print(limit_retries);
    }
    Serial.println(" retries during read-passives!");

    return true;
}

uint8_t pn532_get_chip(Adafruit_PN532 *nfc, uint8_t *uid_buf) {
    // blocking if retries=FF
    // returns the uidLength if a chip is found (4 or 7) otherwise 0
    // stores the uid in *uid too
    uint8_t uid[] = {0, 0, 0, 0, 0, 0, 0};
    uint8_t uidLength;

    Serial.println("Waiting for an ISO14443A chip");
    if (nfc->readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength)) {
        Serial.print("New chip with UID Value: ");
        nfc->PrintHex(uid, uidLength);
        memcpy(uid_buf, uid, 7);
        return uidLength;
    }
    return 0;
}

boolean pn532_peek(Adafruit_PN532 *nfc) {
    // return true if there is a card on the reader
    // returns faster if there IS a card
    uint8_t uid[] = {0, 0, 0, 0, 0, 0, 0};
    uint8_t uidLength;
    return nfc->readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 100);
}

boolean isndef_ntag2xx(Adafruit_PN532 *nfc, uint8_t *uid) {
    // requires caller to use their own uid buf
    uint8_t uidLength = pn532_get_chip(nfc, uid);
    if (uidLength == 7) {
        uint8_t data[32];
        // Check if the NDEF Capability Container (CC) bits are already set in OTP memory (page 3)
        memset(data, 0, 4);
        if (!nfc->ntag2xx_ReadPage(3, data)) {
            Serial.println("Unable to read the Capability Container (page 3)");
            return false;
        }
        // If the tag has already been formatted as NDEF, byte 0 should be:
        // Byte 0 = Magic Number (0xE1)
        // Byte 1 = NDEF Version (Should be 0x10)
        // Byte 2 = Data Area Size (value * 8 bytes)
        // Byte 3 = Read/Write Access (0x00 for full read and write)
        else if (!((data[0] == 0xE1) && (data[1] == 0x10))) {
            Serial.println("This doesn't seem to be an NDEF formatted tag.");
            Serial.println("Page 3 should start with 0xE1 0x10.");
            return false;
        }
        return true;
    }
    return false;
}

boolean read_ntag2xx(Adafruit_PN532 *nfc, uint8_t *data, uint8_t pages_stop, uint8_t pages_start = 0) {
    // assuming the buffer is 4*(pages_stop-pages_start) bytes in size - if not you're gonna have a bad time
    uint8_t uid[]      = {0, 0, 0, 0, 0, 0, 0};
    uint8_t uidLength  = pn532_get_chip(nfc, uid);
    uint8_t pagedata[] = {0, 0, 0, 0};

    if (uidLength == 7) {
        for (uint8_t i = pages_start; i <= pages_stop; i++) {
            // Dump the results
            if (nfc->ntag2xx_ReadPage(i, pagedata)) {
                memcpy(data + 4 * (i - pages_start), pagedata, 4);
            }
            else {
                Serial.println("Unable to read the requested page!");
                return false;
            }
        }
        return true;
    }
    Serial.println("This doesn't seem to be an NTAG2xx (UID length != 7 bytes)");
    return false;
}

boolean updatendef_ntag215(Adafruit_PN532 *nfc, const uint8_t *uid, const char *uri, uint8_t ndefprefix = NDEF_URIPREFIX_NONE) {
    // performs basic CC check to see if the tag is formatted for NDEF
    // must pass the uid acquired from pn532_get_chip, which is assumed length 7
    uint8_t data_area_size;
    uint8_t data[32];
    memset(data, 0, 4);
    if (!nfc->ntag2xx_ReadPage(3, data)) {
        Serial.println("Unable to read the Capability Container (page 3)");
        return false;
    }
    // Determine and display the data area size
    data_area_size = data[2] * 8;
    Serial.print("Tag is NDEF formatted. Data area size = ");
    Serial.print(data_area_size);
    Serial.println(" bytes");

    // Erase the old data area
    Serial.print("Erasing previous data area ");
    for (uint8_t i = 4; i < (data_area_size / 4) + 4; i++) {
        memset(data, 0, 4);
        boolean success = nfc->ntag2xx_WritePage(i, data);
        Serial.print(".");
        if (!success) {
            Serial.println(" ERROR!");
            return false;
        }
    }
    Serial.println();
    Serial.print("Writing URI as NDEF Record ... ");
    if (nfc->ntag2xx_WriteNDEFURI(ndefprefix, uri, data_area_size)) {
        Serial.println("DONE!");
        return true;
    }
    else {
        Serial.println("Error writing NDEFURI?");
        return false;
    }

    return false;
}

boolean readndefentry_ntag215(Adafruit_PN532 *nfc, uint8_t *data, uint16_t *dataLength) {
    // prefix is ignored. todo: dont ignore it?
    // dataLength is the size of your data buffer, and this value will be updated to the size of the retreived data upon success.
    uint8_t readbuffer[504]; // just the user section

    if (!read_ntag2xx(nfc, readbuffer, 129, 4)) {
        Serial.println("bad read");
        return false;
    }
    // we already skipped the manufacturer section, but we skip 12 more bytes of ndef stuff to get to the data
    // reading until we reach the FE byte at the end of the ndef uri
    uint16_t buffer_index = 12;
    uint16_t data_index   = 0;

    while ((data_index < *dataLength - 1) and (buffer_index < 504) and (readbuffer[buffer_index] != 0xFE)) {
        data[data_index] = readbuffer[buffer_index];
        buffer_index++;
        data_index++;
    }
    if ((buffer_index < 504) and (data_index < *dataLength - 1)) {
        // insert null terminator
        data[data_index] = '\0';
        data_index++;
        *dataLength = data_index;
        return true;
    }
    return false;
}

// misc functions
void await_userprompt() {
    Serial.println("----");
    Serial.println("Send a character to continue...");
    Serial.flush();
    while (!Serial.available())
        ;
    while (Serial.available()) {
        Serial.read();
    }
    Serial.flush();
}

void pc_run_command(const char *s) {
    // runs a powershell command through the run dialog
    // powershell exits upon completion
    Keyboard.releaseAll(); // reset

    Keyboard.press(MODIFIERKEY_LEFT_GUI);
    Keyboard.press(KEY_R);
    Keyboard.release(KEY_R);
    Keyboard.release(MODIFIERKEY_LEFT_GUI);
    delay(WIN_RUN_WAIT); // time to hopefully open the RUN dialog
    Keyboard.print("powershell.exe -Command \"");
    Keyboard.print(s);
    Keyboard.print("\"");
    delay(17);
    ; // wait for printing to complete?
    Keyboard.press(KEY_ENTER);
    Keyboard.release(KEY_ENTER);
}

void pc_kill_game(const char *appID, boolean just_alt_f4 = false) {
    // close
    // steam://open/console app_stop <appid> force:1
    // windows+down to minimize
    if (!strcmp(appID, "")) {
        // first time running a game so the buffer hasn't been written
        // do nothing
        return;
    }
    if (!strcmp(appID, "-") || !strcmp(appID, "_")) {
        // the game is not a steam game, do nothing unless altf4 is requested
        if (just_alt_f4) {
            Keyboard.releaseAll();
            Keyboard.press(MODIFIERKEY_LEFT_ALT);
            Keyboard.press(KEY_F4);
            Keyboard.releaseAll();
            return;
        }
    }
    else {
        // we have some steam appID
        Keyboard.releaseAll();

        Keyboard.press(MODIFIERKEY_LEFT_GUI);
        Keyboard.press(KEY_R);
        Keyboard.release(KEY_R);
        Keyboard.release(MODIFIERKEY_LEFT_GUI);
        delay(WIN_RUN_WAIT); // time to hopefully open the RUN dialog
        Keyboard.print("steam://open/console");
        delay(17); // wait for printing to complete?
        Keyboard.press(KEY_ENTER);
        Keyboard.release(KEY_ENTER);
        delay(WIN_RUN_WAIT);     // time to hopefully open the steam console
        Keyboard.press(KEY_TAB); // focus command bar
        Keyboard.release(KEY_TAB);
        // if the command bar was already in focus, it gets populated with 'undefined'; backspace it
        Keyboard.press(MODIFIERKEY_LEFT_CTRL);
        Keyboard.press(KEY_A);
        Keyboard.release(KEY_A);
        Keyboard.release(MODIFIERKEY_LEFT_CTRL);
        Keyboard.press(KEY_BACKSPACE);
        Keyboard.release(KEY_BACKSPACE);
        // enter the command:
        Keyboard.print("app_stop ");
        Keyboard.print(appID);
        Keyboard.print(" force:1");
        delay(17); // wait for printing to complete?
        // todo: check if this needs to be longer/can be shorter.
        // the steam UI is weird and has variable response to key presses, sometimes its slower than windows
        // so the window minimizes before the command is even executed.
        Keyboard.press(KEY_ENTER);
        Keyboard.release(KEY_ENTER);
        Keyboard.press(MODIFIERKEY_LEFT_GUI);
        Keyboard.press(KEY_DOWN);
        Keyboard.release(KEY_DOWN);
        Keyboard.release(MODIFIERKEY_LEFT_GUI);
    }
}

// ### my main functions, which can access these global variables

Adafruit_PN532 g_nfc(PN532_SS); // Hardware SPI connection on Teensy 4.0: CS/SS=10, MOSI=11, MISO=12, SCK=13
Adafruit_NeoPixel g_neopixel(NPXL_LEN, NEOPIXEL_DATA, NEO_GRB + NEO_KHZ800);
IntervalTimer g_neopixelTimer;

void neopixel_handler(const char *mode, uint32_t min_show_ms = 0) {
    // Organize my neopixel calls into one neat function thats interrupt tolerant
    // since only this function calls show, from within interrupt context, the npxl doesn't need to be volatile
    // hard time limit of 100ms (takes ~300us)
    // supporting variable length strips, 1 or 3 leds
    // convey_message[0] can be one of
    // '_': interrupt, called from interrupt during busy mode. must not block, but animate on each call (reading/writing etc)
    // 'C': clear
    // 'F': failure (solid red)
    // 'S': success green
    // 'B': busy (initializes an interrupt timer)
    // 'W': waiting/white (waiting on the user)

    const uint32_t COLOR_FAIL           = 0xB30C2E;
    const uint32_t COLOR_SUCCESS        = 0x0ED45A;
    const uint32_t COLOR_BUSY           = 0xFAAB00;
    const uint32_t COLOR_WHITE          = 0xFFFFE0;
    const unsigned long busyBlinkSwitch = 245;    // ms, but note this function updates at most every bustCheckPeriod-uS
    const int busyCheckPeriod           = 100000; // microseconds between each interrupt

    static elapsedMillis sinceBusyBlink;
    static uint16_t busyBlinker     = NPXL_LEN / 2; // start at 0 unless you have 3 LEDS, then start at 1
    static boolean directionForward = true;

    uint8_t width = g_neopixel.numPixels();

    if ((char) toupper(mode[0]) != '_') {
        busyBlinker = NPXL_LEN / 2; // reset index
        g_neopixelTimer.end();
    }
    switch ((char) toupper(mode[0])) {
    case '_': {
        if (sinceBusyBlink >= busyBlinkSwitch) {
            if (width < 2) {
                // a single pixel just blinks
                g_neopixel.setPixelColor(busyBlinker, g_neopixel.getPixelColor(busyBlinker) ? 0UL : COLOR_BUSY);
            }
            else {
                // a strip of pixels animates
                g_neopixel.setPixelColor(busyBlinker, 0UL);
                if (directionForward) {
                    g_neopixel.setPixelColor(busyBlinker + 1, COLOR_BUSY);
                    if (busyBlinker + 1 == width - 1) {
                        directionForward = false;
                    }
                }
                else {
                    g_neopixel.setPixelColor(busyBlinker - 1, COLOR_BUSY);
                    if (busyBlinker - 1 == 0) {
                        directionForward = true;
                    }
                }
            }
            sinceBusyBlink = 0;
        }
        break;
    }
    case 'B': {
        g_neopixelTimer.begin([]() -> void { neopixel_handler("_interrupt"); }, busyCheckPeriod);
        break;
    }
    case 'C': {
        g_neopixel.clear();
        break;
    }
    case 'F': {
        g_neopixel.fill(COLOR_FAIL);
        break;
    }
    case 'S': {
        g_neopixel.fill(COLOR_SUCCESS);
        break;
    }
    case 'W': {
        g_neopixel.fill(COLOR_WHITE);
        break;
    }
    }
    g_neopixel.setBrightness(10); // oof ouch my eyes
    g_neopixel.show();
    delay(min_show_ms);
}

void do_batchwrite(void) {

    elapsedMillis sinceLastPeek;
    elapsedMillis sinceFullChipWrite;

    neopixel_handler("waiting");
    Serial.println("Starting Batch Write");
    await_userprompt();
    neopixel_handler("busy");

    // steam logic
    uint32_t game_index = 0;
    while (1) {
        if (strlen_P(P_game_list[game_index]) < 1) {
            // all games scanned
            break;
        }

        // get information about game
        // 241 bytes to hold one ndef region record + null char terminator
        char u_gameString_ndefEntry[241] = "";
        strcpy_P(u_gameString_ndefEntry, P_game_list[game_index]);
        const char *mode = "VIASTEAM";
        char *identifier = strstr(u_gameString_ndefEntry, ":") + 1;
        // insert nullchar at id end
        char *id_end       = strstr(identifier, ":");
        *id_end            = '\0';
        char vr_required[] = "N";
        if (*(id_end + 1) == 'Y') {
            strcpy(vr_required, "Y");
        }

        Serial.print("Now writing: \"");
        Serial.print(u_gameString_ndefEntry);
        Serial.print("\" (ID=");
        Serial.print(identifier);
        Serial.print("), vr=");
        Serial.print(vr_required);
        Serial.println("");

        neopixel_handler("waiting", 250); // gives you a little time to pull the previous game away, "debouncing"

        boolean hasCartridge = false;
        while (1) {
            while (sinceLastPeek < 1000 / CHIP_PEEK_POLLING_FREQ) {
                ;
            }
            hasCartridge  = pn532_peek(&g_nfc);
            sinceLastPeek = 0;
            if (sinceFullChipWrite > 500 && hasCartridge) {
                sinceFullChipWrite = 0;
                break;
            }
        }

        // write to chip
        neopixel_handler("busy");
        strcpy(u_gameString_ndefEntry, "");

        strcpy(u_gameString_ndefEntry, mode);
        strcat(u_gameString_ndefEntry, CUSTOM_ASCII_DELIMITER);
        strcat(u_gameString_ndefEntry, identifier);
        strcat(u_gameString_ndefEntry, CUSTOM_ASCII_DELIMITER);
        strcat(u_gameString_ndefEntry, vr_required);
        Serial.print("Preparing to write entry: ");
        Serial.println(u_gameString_ndefEntry);

        uint8_t uid[] = {0, 0, 0, 0, 0, 0, 0};
        boolean success;
        if ((success = isndef_ntag2xx(&g_nfc, uid))) {
            success = updatendef_ntag215(&g_nfc, uid, u_gameString_ndefEntry);
        }
        if (success) {
            neopixel_handler("success");
            Serial.println("Prepare next cartridge");
            while(pn532_peek(&g_nfc)) {
                ;
            }
            game_index += 1;
        }
        else {
            neopixel_handler("failure", 1000);
            Serial.println("Error writing tag, retrying soon");
        }
    }
}

void do_launcher(boolean dryRun = false) {
    // read and launch games
    // assume this is the only function being called repeatedly
    // kills previously running game if necessary
    // only launches if a new game is placed on the reader

    static elapsedMillis sinceLastPeek;
    static elapsedMillis sinceLastFullChipRead;
    static char lastGame[24] = ""; // appID of the last run game

    neopixel_handler("waiting");

    boolean hasCartridge = false;
    while (1) {
        while (sinceLastPeek < 1000 / CHIP_PEEK_POLLING_FREQ) {
            ; // chill
        }
        hasCartridge  = pn532_peek(&g_nfc);
        sinceLastPeek = 0;
        if (sinceLastFullChipRead > 500 && hasCartridge) {
            sinceLastFullChipRead = 0;
            break;
        }
    }

    uint8_t data[240];
    uint16_t dataLength = sizeof(data);

    if (!readndefentry_ntag215(&g_nfc, data, &dataLength)) {
        Serial.println("Chip read error");
        neopixel_handler("failure", 1000);
    }
    else {
        char mode = toupper(data[3]); // v-i-a- S(team), G(og), P(ath), D(olphin)...
        switch (mode) {
        case 'S': {
            // steam game
            // scan ahead to the next delimiters
            char *id_start = strstr((char *) data, CUSTOM_ASCII_DELIMITER) + 1;
            char *id_end   = strstr((char *) id_start, CUSTOM_ASCII_DELIMITER) - 1;
            // boolean vr     = (*(id_end + 2) == 'Y');
            // todo: all the vr launching logic

            char steamCommandBuf[19 + 64] = "start steam://run/";
            uint8_t id_len                = id_end - id_start + 1;
            strncat(steamCommandBuf, id_start, id_len);

            if (strncmp(lastGame, id_start, id_len)) {
                // the game differs from the last game
                neopixel_handler("busy");
                pc_kill_game(lastGame); // kill it (if it was a steam game) so we can run our game instead

                strncpy(lastGame, id_start, id_len);
                Serial.print("RUNNING: ");
                Serial.println(steamCommandBuf);
                if (!dryRun) {
                    pc_run_command(steamCommandBuf);
                }
                neopixel_handler("success");
            }
            else {
                Serial.println("Waiting (same game on reader)");
                neopixel_handler("waiting");
            }
            break;
        }

        case 'G': {
        }
        case 'P': {
        }
        case 'D': {
        }
        }
    }
}

void setup(void) {

    boolean neopixelsWorking = g_neopixel.begin();
    neopixel_handler("clear");

    boolean timersWorking = g_neopixelTimer.begin([]() -> void { neopixel_handler("_interrupt"); }, 50000);
    g_neopixelTimer.priority(254);

    Serial.begin(SERIAL_BAUD);
    if (BATCH_WRITE_MODE || DEBUG_WAIT_FOR_SERIAL) {
        while (!Serial)
            delay(10);
    }

    Serial.println("Serial Connected"); // if the statement isn't true, you aren't going to see it anyways

    if (!timersWorking || !neopixelsWorking) {
        Serial.println("Neopixel/Timer failed initialization, cannot continue.");
        while (1)
            ; // HALT
    }
    if (!init_pn532(&g_nfc)) {
        Serial.println("PN532 failed initialization, cannot continue.");
        neopixel_handler("failure");
        while (1)
            ; // HALT
    }

    // setup all good
    g_neopixelTimer.end();
    neopixel_handler("success", 1000);
}

void loop(void) {
    if (BATCH_WRITE_MODE) {
        do_batchwrite();
        while (1) {
            // batch write complete
            neopixel_handler("success", 1000);
            neopixel_handler("busy", 1000);
        }
    }
    do_launcher();
}