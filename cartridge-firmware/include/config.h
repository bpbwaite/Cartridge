#ifndef CONFIG_H
#define CONFIG_H

#define NPXL_LEN                  (1)    // 1 or 3
#define NPXL_NOTIF_LENGTH         (1000) // ms
#define NPXL_BLINKS_INTERVAL      (245) // ms, 200+
#define WIN_RUN_WAIT              (500)
#define CHIP_PEEK_POLLING_FREQ    (5)    // Hz, max 10
#define PN532_READ_WRITE_DEBOUNCE (1000) // ms
#define USING_RANDOMIZER          (true)

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
#define CUSTOM_ASCII_DELIMITER "\x0BF" // ndef compatible, upside down question mark delimiter
#define APPID_BUFS_MAX (24)

#endif