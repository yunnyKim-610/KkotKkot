/*
 * UWB 칩(Qorvo DW3000 계열) SPI 연결 확인 - 구현
 *
 * SPI 헤더 형식 (DW3000 User Manual, Qorvo 드라이버 dwt_xfer3000 기준)
 *  - 오프셋 0 레지스터 읽기는 1바이트 "짧은 주소" 헤더를 쓴다.
 *    header = (reg_file << 1) | 0x01, 쓰기면 bit7(0x80)을 켠다.
 *  - 값은 리틀 엔디언으로 돌아온다.
 *
 * 칩 PLL이 잠기기 전에는 SPI를 느리게(수 MHz 이하) 돌려야 하므로 초기 클럭은 Kconfig 기본 2MHz.
 */
#include "uwb_spi.h"

#include <string.h>
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_check.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"

static const char *TAG = "uwb-spi";

#define UWB_REG_DEV_ID       0x00   /* 레지스터 파일 0, 오프셋 0 */
#define UWB_SPI_SHORT_READ   0x01   /* 짧은 주소 헤더 표시 비트 */

static spi_device_handle_t s_dev;

esp_err_t uwb_spi_init(void)
{
    const spi_bus_config_t bus = {
        .mosi_io_num = CONFIG_KKOT_UWB_PIN_MOSI,
        .miso_io_num = CONFIG_KKOT_UWB_PIN_MISO,
        .sclk_io_num = CONFIG_KKOT_UWB_PIN_SCLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 64,
    };
    ESP_RETURN_ON_ERROR(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_DISABLED), TAG, "SPI 버스 초기화 실패");

    const spi_device_interface_config_t dev = {
        .mode = 0,                                       /* DW3000: CPOL=0, CPHA=0 */
        .clock_speed_hz = CONFIG_KKOT_UWB_SPI_SLOW_HZ,
        .spics_io_num = CONFIG_KKOT_UWB_PIN_CS,
        .queue_size = 1,
    };
    ESP_RETURN_ON_ERROR(spi_bus_add_device(SPI2_HOST, &dev, &s_dev), TAG, "SPI 장치 등록 실패");

#if CONFIG_KKOT_UWB_PIN_RST >= 0
    /* RSTn은 칩 내부 풀업이 있고 외부에서 High로 구동하면 안 된다. 평소에는 입력(High-Z)으로 둔다. */
    gpio_reset_pin(CONFIG_KKOT_UWB_PIN_RST);
    gpio_set_direction(CONFIG_KKOT_UWB_PIN_RST, GPIO_MODE_INPUT);
#endif
    return ESP_OK;
}

void uwb_spi_hard_reset(void)
{
#if CONFIG_KKOT_UWB_PIN_RST >= 0
    gpio_set_level(CONFIG_KKOT_UWB_PIN_RST, 0);
    gpio_set_direction(CONFIG_KKOT_UWB_PIN_RST, GPIO_MODE_OUTPUT_OD);
    esp_rom_delay_us(10);                                  /* 최소 펄스 폭보다 넉넉히 */
    gpio_set_direction(CONFIG_KKOT_UWB_PIN_RST, GPIO_MODE_INPUT);
#endif
    vTaskDelay(pdMS_TO_TICKS(5));                          /* 칩 기동(INIT_RC) 대기 */
}

esp_err_t uwb_spi_read_dev_id(uint32_t *dev_id)
{
    uint8_t tx[5] = { (uint8_t)((UWB_REG_DEV_ID << 1) | UWB_SPI_SHORT_READ), 0, 0, 0, 0 };
    uint8_t rx[5] = { 0 };
    spi_transaction_t t = {
        .length = sizeof(tx) * 8,
        .tx_buffer = tx,
        .rx_buffer = rx,
    };
    ESP_RETURN_ON_ERROR(spi_device_polling_transmit(s_dev, &t), TAG, "SPI 전송 실패");
    *dev_id = (uint32_t)rx[1] | ((uint32_t)rx[2] << 8) | ((uint32_t)rx[3] << 16) | ((uint32_t)rx[4] << 24);
    return ESP_OK;
}

const char *uwb_dev_id_name(uint32_t dev_id)
{
    switch (dev_id) {
    case 0xDECA0302: return "DW3000 계열 (단일 안테나, DW3110 등)";
    case 0xDECA0312: return "DW3000 계열 PDoA (듀얼 안테나, DW3220 등)";
    default:         return NULL;
    }
}
