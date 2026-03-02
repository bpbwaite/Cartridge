#ifndef UTIL_H
#define UTIL_H

#include "config.h"

#include <Arduino.h>
#include <Adafruit_PN532.h>

void await_userprompt(void);

void pc_run_command(const char *s);

void pc_kill_game(const char *appID, boolean just_alt_f4 = false);

uint32_t get_random_gameID(void);

boolean pn532_init(Adafruit_PN532 *nfc, uint8_t limit_retries = 0xFF);

uint8_t pn532_get_chip(Adafruit_PN532 *nfc, uint8_t *uid_buf);

boolean pn532_peek(Adafruit_PN532 *nfc);

boolean isndef_ntag2xx(Adafruit_PN532 *nfc, uint8_t *uid);

boolean read_ntag2xx(Adafruit_PN532 *nfc, uint8_t *data, uint8_t pages_stop, uint8_t pages_start = 0);

boolean updatendef_ntag215(Adafruit_PN532 *nfc, const uint8_t *uid, const char *uri, uint8_t ndefprefix = NDEF_URIPREFIX_NONE);

boolean readndefentry_ntag215(Adafruit_PN532 *nfc, uint8_t *data, uint16_t *dataLength);

#endif