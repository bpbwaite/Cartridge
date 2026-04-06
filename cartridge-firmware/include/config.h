#ifndef CONFIG_H
#define CONFIG_H

#include <Keyboard.h>

#define NPXL_LEN                  (3)    // 1 or 3
#define NPXL_NOTIF_LENGTH         (900) // ms
#define NPXL_BLINKS_INTERVAL      (225) // ms, 200+
#define WIN_RUN_WAIT              (500)
#define CHIP_PEEK_POLLING_FREQ    (5)    // Hz, max 10
#define PN532_READ_WRITE_DEBOUNCE (1000) // ms
#define USING_RANDOMIZER          (true)
#define ALTF4_ANY                 (false) // set true to send ALT-F4 before launching a game while a non-steam game is currently running
#define VR_HOTKEY_SEQUENCE        {MODIFIERKEY_LEFT_CTRL, MODIFIERKEY_LEFT_ALT, MODIFIERKEY_LEFT_SHIFT, KEY_F12}

// Pinout
#define PIN_NPXL_DATA     (2)
#define PIN_DIP1          (6)
#define PIN_DIP2          (4)
#define PIN_DIP3          (3)
#define PIN_PN532_CS      (10)
#define SPI_RESERVED_MOSI (11)
#define SPI_RESERVED_MISO (12)
#define SPI_RESERVED_SCK  (13)

// Expert zone (do not modify)
#define NDEF_SECTOR_BYTES (240)
#define CUSTOM_ASCII_DELIMITER "\x0BF" // ndef compatible, upside down question mark delimiter
#define APPID_BUFS_MAX (24)
#define CMD_BUFS_MAX (NDEF_SECTOR_BYTES - 17) // maximum command size that will fit (?) in a sector
#define KEYBOARD_BW_HZ (62) // compatibility value. maximum keystrokes (press and release) per second supported by the OS HID driver. can vary 62.5 - 500

#endif