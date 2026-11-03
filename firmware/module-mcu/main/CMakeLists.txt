idf_component_register(SRCS "main.c" "uwb_spi.c"
                       INCLUDE_DIRS "."
                       PRIV_REQUIRES esp_driver_spi esp_driver_gpio)
