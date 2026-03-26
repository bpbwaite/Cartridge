#include "util.h"

// helpful i/o functions

void print_eeprom(void) {
    const uint32_t eeprom_size = E2END + 1;
    Serial.print("[");
    for (uint32_t i = 0; i < eeprom_size; i++) {
        if ((i > 0) && (i % sizeof(uint32_t) == 0)) {
            Serial.print("][");
        }
        uint8_t eri = EEPROM.read(i);
        if (eri < 0x10) {
            Serial.print('0');
        }
        Serial.print(eri, HEX);
    }
    Serial.println("]");
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
    delay(17); // wait for printing to complete?
    Keyboard.press(KEY_ENTER);
    Keyboard.release(KEY_ENTER);
}

void pc_kill_game(const char *appID, boolean just_alt_f4) {
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
        // kill it so we can run our game instead
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
        delay(250); // wait for printing to complete?
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

// PN532 functions

boolean pn532_init(Adafruit_PN532 *nfc, uint8_t limit_retries) {
    nfc->begin();
    uint32_t versiondata = nfc->getFirmwareVersion();
    if (!versiondata) {
        Serial.println("Didn't find PN53x board");
        return false;
    }
    Serial.print("Found chip PN5");
    Serial.print((versiondata >> 24) & 0xFF, HEX);
    Serial.print(" ver. ");
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
        Serial.print("Found chip with UID Value: ");
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

boolean read_ntag2xx(Adafruit_PN532 *nfc, uint8_t *data, uint8_t pages_stop, uint8_t pages_start) {
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

boolean updatendef_ntag215(Adafruit_PN532 *nfc, const uint8_t *uid, const char *uri, uint8_t ndefprefix) {
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
    // prefix is ignored.
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