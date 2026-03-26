#include <Arduino.h>
#include <Entropy.h>
#include <FastCRC.h>

#include <Adafruit_NeoPixel.h>
#include <Adafruit_PN532.h>

#include "config.h"
#include "batch_game_list.h"
#include "util.h"

Adafruit_NeoPixel g_neopixel(NPXL_LEN, PIN_NPXL_DATA, NEO_GRB + NEO_KHZ800);
Adafruit_PN532 g_nfc(PIN_PN532_CS); // Hardware SPI connection on Teensy 4.0
IntervalTimer g_neopixelTimer;
IntervalTimer g_tempRoutineTimer;
FastCRC8 g_CRC8;

uint8_t dipSwitches = 0b000; // debug|batchWrite|closePrev

// ### my main functions, which can access these global variables

void updateDipSwitches(void) {
    // DIP reads inverted logic when input is pullup
    dipSwitches = (!digitalRead(PIN_DIP1) << 2) | (!digitalRead(PIN_DIP2) << 1) | (!digitalRead(PIN_DIP3) << 0);
}

void neopixel_handler(const char *mode, uint32_t min_show_ms = 0) {
    // Organize my neopixel calls into one neat function thats interrupt tolerant
    // since only this function calls show, from within interrupt context, the npxl doesn't need to be volatile
    // hard time limit of 100ms (takes ~300us)
    // supporting variable length strips, 1 or 3 leds
    // mode[0] can be one of
    // '_': interrupt, called from interrupt during busy mode. must not block, but animate on each call (reading/writing etc)
    // 'C': clear
    // 'F': failure (solid red)
    // 'S': success green
    // 'B': busy (initializes an interrupt timer)
    // 'W': waiting/white (waiting on the user)

    const uint32_t COLOR_FAIL        = 0xB30C2E;
    const uint32_t COLOR_SUCCESS     = 0x0ED45A;
    const uint32_t COLOR_BUSY        = 0xFAAB00;
    const uint32_t COLOR_WAITING     = 0xFFFFE0;
    const uint32_t COLOR_OVERHEATING = 0xFF0000;

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
        if (sinceBusyBlink >= NPXL_BLINKS_INTERVAL) {
            if (width < 2) {
                // a single pixel just blinks
                g_neopixel.setPixelColor(busyBlinker, g_neopixel.getPixelColor(busyBlinker) ? 0UL : COLOR_BUSY);
            }
            else {
                // a strip of pixels animates
                g_neopixel.setPixelColor(busyBlinker, 0UL);
                if (directionForward) {
                    busyBlinker += 1;
                    g_neopixel.setPixelColor(busyBlinker, COLOR_BUSY);
                    if (busyBlinker == width - 1) {
                        directionForward = false;
                    }
                }
                else {
                    busyBlinker -= 1;
                    g_neopixel.setPixelColor(busyBlinker, COLOR_BUSY);
                    if (busyBlinker == 0) {
                        directionForward = true;
                    }
                }
            }
            sinceBusyBlink = 0;
        }
        break;
    }
    case 'B': {
        g_neopixel.clear();
        g_neopixelTimer.begin([]() -> void { neopixel_handler("_interrupt"); }, busyCheckPeriod);
        break;
    }
    case 'H': {
        // hot - ideally, min_show_ms != 0
        if (min_show_ms <= 0) {
            min_show_ms = 1000;
        }
        elapsedMillis sinceOverheat;
        while (sinceOverheat < min_show_ms) {
            // rapidly blink red
            g_neopixel.fill(COLOR_OVERHEATING);
            g_neopixel.show();
            delay(50);
            g_neopixel.clear();
            g_neopixel.show();
            delay(50);
        }
        return; // return, as this case has its own call to show()
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
        if (NPXL_LEN == 1) {
        g_neopixel.fill(COLOR_WAITING);
        }
        else if (NPXL_LEN == 3) {
            g_neopixel.clear();
            g_neopixel.setPixelColor(1, COLOR_WAITING);
        }
        break;
    }
    }
    g_neopixel.setBrightness(10); // oof ouch my eyes
    g_neopixel.show();
    delay(min_show_ms);
}

void temp_checker(void) {
    float coreTempC = tempmonGetTemp();
    if (coreTempC > float(85.0)) {
        Serial.print("Core temperature: ");
        Serial.print(coreTempC);
        Serial.println(" is very hot!");
        neopixel_handler("hot", 5000);
        // just a warning;
        // we can keep running, the teensy will panic halt if it hits a dangerous 95C
    }
}

uint32_t get_random_gameID(void) {

    if (!USING_RANDOMIZER) {
        return 0;
    }
    uint8_t appID_list_size = EEPROM.read(0);
    
    Serial.println("Writing EEPROM");
    Serial.flush();
    Serial.clear();
    
    Serial.println("<RANDOMGAMES>");
    while(!Serial.available())
        ;
    // script sends raw bytes, not utf-8.
    // the first byte written to the eeprom will tell us the number of entries (4 bytes each)
    uint8_t n = Serial.read();
    uint32_t maxbytes = n * sizeof(uint32_t);
    
    EEPROM.write(0, n);
    
    uint32_t idx = 0;
    while (idx < maxbytes) {
        int ebyte = Serial.read();
        if (ebyte == -1) {
            delay(10);
            continue; // the sender must transmit n bytes total to break this loop, todo: a restting max-retries limit
        }
        
        EEPROM.write(idx + sizeof(uint32_t), ebyte);
        idx++;
    }
    Serial.println("Finshed writing EEPROM");
    //Serial.println("Finshed writing EEPROM, contents:");
    //print_eeprom();
    // EEPROM.read(1);
    // EEPROM.read(2);
    // EEPROM.read(3);
    // todo: use EEPROM get and set instead
    uint32_t id_start = ((random() % appID_list_size) + 1) * sizeof(uint32_t); // we add one so we don't get the list size
    
    return
    uint32_t(EEPROM.read(id_start + 0) << 24) + 
    uint32_t(EEPROM.read(id_start + 1) << 16) + 
    uint32_t(EEPROM.read(id_start + 2) << 8) + 
    uint32_t(EEPROM.read(id_start + 3) << 0) ; // casts prevent overflow
}

void quick_make_random_cartridge(void) {
    Serial.println("Place randomizer cartridge on reader");
    await_userprompt();
    uint8_t uid[] = {0, 0, 0, 0, 0, 0, 0};
    pn532_get_chip(&g_nfc, uid);
    updatendef_ntag215(&g_nfc, uid, "VIASTEAM" CUSTOM_ASCII_DELIMITER "RANDOM" CUSTOM_ASCII_DELIMITER "N" CUSTOM_ASCII_DELIMITER "1E");
}

void do_batchwrite(void) {

    neopixel_handler("waiting");
    Serial.println("Starting Batch Write");
    await_userprompt();
    neopixel_handler("busy");

    // steam logic
    uint32_t gameIndex = 0;
    while (1) {
        if (strlen_P(P_game_list[gameIndex]) < 1) {
            // all games scanned
            break;
        }

        // get information about game
        // 241 bytes to hold one ndef region record + null char terminator
        char u_gameString_ndefEntry[241] = "";
        strcpy_P(u_gameString_ndefEntry, P_game_list[gameIndex]);
        const char *mode = "VIASTEAM";
        char *identifier = strstr(u_gameString_ndefEntry, ":") + 1;
        // insert nullchar at id end
        char *id_end       = strstr(identifier, ":");
        *id_end            = '\0';
        char vr_required[] = "N";
        if (*(id_end + 1) == 'Y') {
            strcpy(vr_required, "Y");
        }

        // compute CRC
        const char hex_chars[] = "0123456789ABCDEF";

        uint8_t crc_raw = g_CRC8.smbus((uint8_t *) identifier, strlen(identifier));
        char crc_hex[3] = "00";
        crc_hex[0]      = hex_chars[(crc_raw >> 4) & 0xF];
        crc_hex[1]      = hex_chars[crc_raw & 0xF];

        Serial.print("Now writing: \"");
        Serial.print(u_gameString_ndefEntry);
        Serial.print("\" (ID=");
        Serial.print(identifier);
        Serial.print("), vr=");
        Serial.print(vr_required);
        Serial.print(", CRC=0x");
        Serial.print(crc_hex);
        Serial.println(".");
        Serial.println("(X to skip)");

        neopixel_handler("waiting", PN532_READ_WRITE_DEBOUNCE); // gives you a little time to pull the previous game away, "debouncing"

        while (1) {
            delay(1000 / CHIP_PEEK_POLLING_FREQ);
            if (pn532_peek(&g_nfc) || Serial.available()) {
                break;
            }
        }
        if (!Serial.available()) {

            // write to chip
            neopixel_handler("busy");
            strcpy(u_gameString_ndefEntry, "");

            strcpy(u_gameString_ndefEntry, mode);
            strcat(u_gameString_ndefEntry, CUSTOM_ASCII_DELIMITER);
            strcat(u_gameString_ndefEntry, identifier);
            strcat(u_gameString_ndefEntry, CUSTOM_ASCII_DELIMITER);
            strcat(u_gameString_ndefEntry, vr_required);
            strcat(u_gameString_ndefEntry, CUSTOM_ASCII_DELIMITER);
            strcat(u_gameString_ndefEntry, crc_hex);

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
                while (pn532_peek(&g_nfc)) {
                    delay(50);
                }
                gameIndex += 1;
            }
            else {
                neopixel_handler("failure", NPXL_NOTIF_LENGTH);
                Serial.println("Error writing tag, retrying soon");
            }
        }
        else {
            // skipped
            gameIndex += 1;
        }
    }
}

void do_launcher(boolean dryRun = false) {
    // read and launch games
    // assume this is the only function being called repeatedly
    // kills previously running game if necessary
    // only launches if a new game is placed on the reader

    static elapsedMillis sinceLastFullChipRead;
    static char lastGame[APPID_BUFS_MAX] = ""; // appID of the last run game

    neopixel_handler("waiting");

    boolean hasCartridge = pn532_peek(&g_nfc);
    while (hasCartridge) {
        delay(1000 / CHIP_PEEK_POLLING_FREQ);
        hasCartridge = pn532_peek(&g_nfc);
    }
    while (1) {
        delay(1000 / CHIP_PEEK_POLLING_FREQ);
        hasCartridge = pn532_peek(&g_nfc);
        if (sinceLastFullChipRead > PN532_READ_WRITE_DEBOUNCE && hasCartridge) {
            sinceLastFullChipRead = 0;
            break;
        }
    }

    uint8_t data[240];
    uint16_t dataLength = sizeof(data);

    if (!readndefentry_ntag215(&g_nfc, data, &dataLength)) {
        Serial.println("Chip read error");
        neopixel_handler("failure", NPXL_NOTIF_LENGTH);
    }
    else {
        char mode = toupper(data[3]); // v-i-a- S(team), G(og), P(ath), D(olphin)...
        switch (mode) {
        case 'S': {
            // steam game
            // scan ahead to the next delimiters
            char *id_start = strstr((char *) data, CUSTOM_ASCII_DELIMITER) + 1;
            char *id_end   = strstr((char *) id_start, CUSTOM_ASCII_DELIMITER) - 1;
            uint8_t id_len = id_end - id_start + 1;
            boolean vr     = (*(id_end + 2) == 'Y');
            // todo: all the vr launching logic
            // todo: read and confirm checksum bytes

            if (strncmp(lastGame, id_start, id_len)) {
                char steamCommandBuf[19 + APPID_BUFS_MAX] = "start steam://run/";
                // the game differs from the last game
                neopixel_handler("busy");
                // check if the game identifier is 'random' and launch a random game instead
                if (!strncmp("RANDOM", id_start, id_len)) {
                    char appIDitoa_buf[APPID_BUFS_MAX];
                    uint32_t randomID = get_random_gameID();
                    if (randomID == 0) {
                        // random games list wasn't set up properly
                        Serial.println("Issue with random games list");
                        neopixel_handler("failure", NPXL_NOTIF_LENGTH);
                        break;
                    }
                    itoa(randomID, appIDitoa_buf, 10);
                    strcat(steamCommandBuf, appIDitoa_buf);
                    if (!dryRun && (dipSwitches & 0b001)) {
                        pc_kill_game(lastGame);
                    }
                    strcpy(lastGame, appIDitoa_buf);
                }
                else {
                    strncat(steamCommandBuf, id_start, id_len);
                    if (!dryRun && (dipSwitches & 0b001)) {
                        pc_kill_game(lastGame);
                    }
                    strncpy(lastGame, id_start, id_len);
                }

                Serial.print("Running: ");
                Serial.println(steamCommandBuf);
                if (!dryRun) {
                    pc_run_command(steamCommandBuf);
                }
                neopixel_handler("success", NPXL_NOTIF_LENGTH);
            }
            else {
                Serial.println("Waiting (same game on reader)");
                neopixel_handler("waiting");
            }
            break;
        }

        // these modes need to reset the lastGame variable to "\0" for steam mode so pc_kill_game doesn't try to close a game that's not running
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
    // hardware setup
    pinMode(PIN_DIP1, INPUT_PULLUP);
    pinMode(PIN_DIP2, INPUT_PULLUP);
    pinMode(PIN_DIP3, INPUT_PULLUP);
    pinMode(LED_BUILTIN, OUTPUT); // note: LED builtin is also SCK for SPI
    delayMicroseconds(3);

    // todo: watchdog configuration

    boolean neopixelsWorking = g_neopixel.begin();
    neopixel_handler("clear");
    boolean timersWorking = g_neopixelTimer.begin([]() -> void { neopixel_handler("_interrupt"); }, 50000) && g_tempRoutineTimer.begin(temp_checker, 10000000);
    g_neopixelTimer.priority(254);
    g_tempRoutineTimer.priority(253);

    Entropy.Initialize();

    updateDipSwitches();

    if ((dipSwitches & 0b100) || (dipSwitches & 0b010)) {
        while (!Serial) {
            delay(10);
        }
    }

    Serial.println("Serial Connected"); // if the statement isn't true, you aren't going to see it anyways
    Serial.print("Firmware built on ");
    Serial.println(COMPILE_TIME); // todo: unix epoch to date/time/timezone thing
    if (!timersWorking) {
        Serial.println("A timer failed initialization, cannot continue.");
        while (1)
            ; // HALT
    }
    if (!neopixelsWorking) {
        Serial.println("Neopixel failed initialization, cannot continue.");
        while (1)
            ; // HALT
    }
    if (!pn532_init(&g_nfc)) {
        Serial.println("PN532 failed initialization, cannot continue.");
        neopixel_handler("failure");
        while (1)
            ; // HALT
    }

    elapsedMillis sinceEntropyExpected;
    while (!Entropy.available()) {
        if (sinceEntropyExpected > 5000) {
            // some issue with rng
            // srandom will receive 0
            Serial.println("RNG failure, continuing anyways");
            break;
        }
    }
    uint32_t randomSeed = Entropy.random();
    Serial.print("Using random seed ");
    Serial.println(randomSeed);
    srandom(randomSeed);

    Serial.print("DIP Config (debug|batchWrite|closePrev) = ");
    Serial.print(dipSwitches, 2);
    Serial.print("-");
    Serial.println(dipSwitches);

    // setup all good
    g_neopixelTimer.end();
    neopixel_handler("success", NPXL_NOTIF_LENGTH);
    // quick_make_random_cartridge();
}

void loop(void) {

    static boolean batch_write_complete = false;
    if ((dipSwitches & 0b010) && !batch_write_complete) {
        do_batchwrite();
        neopixel_handler("busy", NPXL_NOTIF_LENGTH);
        Serial.println("Batch game writing is all done!");
        neopixel_handler("success", NPXL_NOTIF_LENGTH);
        batch_write_complete = true;
    }

    do_launcher(true);
}