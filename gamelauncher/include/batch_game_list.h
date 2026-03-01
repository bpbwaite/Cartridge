#ifndef BATCH_GAME_LIST_H
#define BATCH_GAME_LIST_H

#include <Arduino.h>

#define FLASH_LISTS_NOT_INITIALIZED // this line is removed by running the python script.

static const char* const P_game_list[] PROGMEM = {
    // null terminate this buf
    "\0"
};

static const uint32_t PROGMEM P_appID_list[] = {};

#endif
