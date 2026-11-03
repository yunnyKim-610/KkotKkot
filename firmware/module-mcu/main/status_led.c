/*
 * 상태 LED 구동
 *
 * WS2812: RMT bytes encoder, 10MHz 해상도(0.1us).
 *   0 = 0.3us High + 0.9us Low, 1 = 0.9us High + 0.3us Low, 색 순서 GRB.
 *   한 번 보낸 뒤 선이 Low로 유지되면(>50us) LED가 값을 반영한다.
 * 단색: GPIO 출력. ACTIVE_LOW면 LOW일 때 켜진다 (XIAO ESP32S3 GPIO21).
 */
#include "status_led.h"

#include "esp_check.h"
#include "sdkconfig.h"

#if CONFIG_KKOT_STATUS_LED_WS2812
#include "driver/rmt_encoder.h"
#include "driver/rmt_tx.h"
#else
#include "driver/gpio.h"
#endif

static const char *TAG = "status-led";

#if CONFIG_KKOT_STATUS_LED_GPIO < 0
/* ---------- LED 없음 ---------- */

esp_err_t status_led_init(void) { return ESP_OK; }
esp_err_t status_led_set(uint8_t r, uint8_t g, uint8_t b) { (void)r; (void)g; (void)b; return ESP_OK; }
bool status_led_has_color(void) { return false; }

#elif CONFIG_KKOT_STATUS_LED_WS2812
/* ---------- WS2812 RGB ---------- */

#define LED_RMT_HZ  10000000

static rmt_channel_handle_t s_chan;
static rmt_encoder_handle_t s_enc;

esp_err_t status_led_init(void)
{
    const rmt_tx_channel_config_t ch = {
        .gpio_num = CONFIG_KKOT_STATUS_LED_GPIO,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = LED_RMT_HZ,
        .mem_block_symbols = 64,
        .trans_queue_depth = 2,
    };
    ESP_RETURN_ON_ERROR(rmt_new_tx_channel(&ch, &s_chan), TAG, "RMT 채널 생성 실패");

    const rmt_bytes_encoder_config_t enc = {
        .bit0 = { .level0 = 1, .duration0 = 3, .level1 = 0, .duration1 = 9 },
        .bit1 = { .level0 = 1, .duration0 = 9, .level1 = 0, .duration1 = 3 },
        .flags.msb_first = 1,
    };
    ESP_RETURN_ON_ERROR(rmt_new_bytes_encoder(&enc, &s_enc), TAG, "RMT 인코더 생성 실패");
    ESP_RETURN_ON_ERROR(rmt_enable(s_chan), TAG, "RMT 활성화 실패");
    return status_led_set(0, 0, 0);
}

esp_err_t status_led_set(uint8_t r, uint8_t g, uint8_t b)
{
    if (s_chan == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    static uint8_t grb[3];   /* 전송이 끝날 때까지 유효해야 하므로 static */
    ESP_RETURN_ON_ERROR(rmt_tx_wait_all_done(s_chan, 10), TAG, "이전 전송 대기 실패");
    grb[0] = g; grb[1] = r; grb[2] = b;
    const rmt_transmit_config_t tx = { .loop_count = 0 };
    return rmt_transmit(s_chan, s_enc, grb, sizeof(grb), &tx);
}

bool status_led_has_color(void) { return true; }

#else
/* ---------- 단색 LED ---------- */

#if CONFIG_KKOT_STATUS_LED_ACTIVE_LOW
#define LED_ON_LEVEL  0
#else
#define LED_ON_LEVEL  1
#endif

esp_err_t status_led_init(void)
{
    ESP_RETURN_ON_ERROR(gpio_reset_pin(CONFIG_KKOT_STATUS_LED_GPIO), TAG, "GPIO 초기화 실패");
    ESP_RETURN_ON_ERROR(gpio_set_direction(CONFIG_KKOT_STATUS_LED_GPIO, GPIO_MODE_OUTPUT), TAG, "GPIO 방향 설정 실패");
    return status_led_set(0, 0, 0);
}

esp_err_t status_led_set(uint8_t r, uint8_t g, uint8_t b)
{
    const bool on = (r | g | b) != 0;
    return gpio_set_level(CONFIG_KKOT_STATUS_LED_GPIO, on ? LED_ON_LEVEL : !LED_ON_LEVEL);
}

bool status_led_has_color(void) { return false; }

#endif
