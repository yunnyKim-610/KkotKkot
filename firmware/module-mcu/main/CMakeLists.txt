set(srcs "main.c" "mcu_frame.c" "status_led.c")
if(CONFIG_KKOT_UWB_ENABLE)
    list(APPEND srcs "uwb_spi.c")
endif()

idf_component_register(SRCS ${srcs}
                       INCLUDE_DIRS "."
                       PRIV_REQUIRES esp_driver_spi esp_driver_gpio esp_driver_rmt
                                     esp_driver_uart esp_driver_usb_serial_jtag esp_timer)
