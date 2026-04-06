#ifndef UTIL_H
#define UTIL_H

#include "config.h"

#include <Arduino.h>
#include <Adafruit_PN532.h>
#include <EEPROM.h>

#define DIPSW_STD        0b000
#define DIPSW_STD_AC     0b001
#define DIPSW_STD_VR     0b010
#define DIPSW_STD_VR_AC  0b011
#define DIPSW_WFSM       0b100
#define DIPSW_WFSM_VR_AC 0b101
#define DIPSW_SECRETMODE 0b110
#define DIPSW_BATCHWRITE 0b111

boolean isDSAC(uint8_t ds);

boolean isDSVR(uint8_t ds);

boolean isDSWFSM(uint8_t ds);

void print_eeprom(void);

void pc_send_vr_hotkey(void);

void pc_run_command(const char *s);

void pc_kill_game(const char *appID, boolean just_alt_f4 = false);

boolean pn532_init(Adafruit_PN532 *nfc, uint8_t limit_retries = 0xFF);

uint8_t pn532_get_chip(Adafruit_PN532 *nfc, uint8_t *uid_buf);

boolean pn532_peek(Adafruit_PN532 *nfc);

boolean isndef_ntag2xx(Adafruit_PN532 *nfc, uint8_t *uid);

boolean read_ntag2xx(Adafruit_PN532 *nfc, uint8_t *data, uint8_t pages_stop, uint8_t pages_start = 0);

boolean updatendef_ntag215(Adafruit_PN532 *nfc, const uint8_t *uid, const char *uri, uint8_t ndefprefix = NDEF_URIPREFIX_NONE);

boolean readndefentry_ntag215(Adafruit_PN532 *nfc, uint8_t *data, uint16_t *dataLength);

#endif