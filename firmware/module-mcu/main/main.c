/*
 * 꼿꼿 센싱 모듈 보조 MCU (ESP32-S3, ESP-IDF) - 뼈대
 *
 * 태스크 구성 (FreeRTOS)
 *  - power_task    : 입력 전압 감시(ADC), 저하 시 Jetson에 종료 요청 GPIO
 *  - watchdog_task : Jetson 하트비트 확인, 끊기면 Jetson 재시작 GPIO
 *  - uwb_task      : UWB 방향 측정 칩(SPI) 처리 (KKOT_UWB_ENABLE 일 때만)
 *  - uart_task     : Jetson과 프레임 송수신 (UART1 또는 단독 테스트용 USB)
 *  - can_task      : 로봇 본체와 TWAI(CAN) 통신
 *
 * 원칙: Wi-Fi/BLE 무선은 사용하지 않는다 (Jetson이 담당). 안전 기능이 무선 스택에 영향받지 않게 한다.
 */
#include <inttypes.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"

#include "mcu_frame.h"
#include "status_led.h"
#if CONFIG_KKOT_UWB_ENABLE
#include "uwb_spi.h"
#endif
#if CONFIG_KKOT_LINK_USB_SERIAL_JTAG
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#else
#include "driver/uart.h"
#endif

static const char *TAG = "kkotkkot-mcu";

/* bool Kconfig는 꺼지면 매크로가 정의되지 않으므로 C 조건식용 값을 따로 둔다 */
#if CONFIG_KKOT_UWB_ENABLE
#define UWB_ENABLED 1
#else
#define UWB_ENABLED 0
#endif

/* 마지막 하트비트 시각(us). watchdog_task가 읽는다. */
static volatile int64_t s_last_heartbeat_us;

/* ---------- Jetson 연결 통로 ---------- */

static esp_err_t link_init(void)
{
#if CONFIG_KKOT_LINK_USB_SERIAL_JTAG
    /* 로그(콘솔)와 프레임 수신이 같은 USB를 쓴다. 로그도 드라이버를 거치게 해야 서로 충돌하지 않는다.
       (sdkconfig.solo 에서 USB-Serial-JTAG를 기본 콘솔로 지정) */
    usb_serial_jtag_driver_config_t cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    esp_err_t err = usb_serial_jtag_driver_install(&cfg);
    if (err == ESP_OK) {
        usb_serial_jtag_vfs_use_driver();
    }
    return err;
#else
    const uart_config_t cfg = {
        .baud_rate = CONFIG_KKOT_LINK_UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    esp_err_t err = uart_driver_install(UART_NUM_1, 512, 0, 0, NULL, 0);
    if (err == ESP_OK) err = uart_param_config(UART_NUM_1, &cfg);
    if (err == ESP_OK) err = uart_set_pin(UART_NUM_1, CONFIG_KKOT_LINK_UART_TX, CONFIG_KKOT_LINK_UART_RX,
                                          UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    return err;
#endif
}

static int link_read(uint8_t *buf, size_t len, TickType_t wait)
{
#if CONFIG_KKOT_LINK_USB_SERIAL_JTAG
    return usb_serial_jtag_read_bytes(buf, len, wait);
#else
    return uart_read_bytes(UART_NUM_1, buf, len, wait);
#endif
}

/* ---------- 알림 처리 ---------- */

#ifdef CONFIG_KKOT_STATUS_LED_BRIGHTNESS
#define LED_BRIGHTNESS CONFIG_KKOT_STATUS_LED_BRIGHTNESS
#else
#define LED_BRIGHTNESS 255   /* 단색 LED는 켜짐/꺼짐만 쓴다 */
#endif
static int64_t s_led_start_us;    /* 알림 표시 시작 시각 */
static int64_t s_led_off_at_us;   /* 0이면 꺼져 있음 */
static uint8_t s_led_level;

/* 알림 표시 중 LED 갱신. 색 LED는 시작 때 한 번 켜고, 단색 LED는 단계별 주기로 깜빡인다. */
static void led_update(int64_t now)
{
    if (s_led_off_at_us == 0) {
        return;
    }
    if (now >= s_led_off_at_us) {
        status_led_set(0, 0, 0);
        s_led_off_at_us = 0;
        return;
    }
#if CONFIG_KKOT_STATUS_LED_GPIO_PLAIN
    /* 단색 LED: 단계별 주기로 깜빡임 (색 LED는 handle_alert에서 한 번 켜 두면 된다) */
    const int64_t period_us = (int64_t)(s_led_level >= 2 ? CONFIG_KKOT_ALERT_BLINK_FAST_MS
                                                        : CONFIG_KKOT_ALERT_BLINK_SLOW_MS) * 1000;
    const bool on = period_us <= 0 || ((now - s_led_start_us) % period_us) < period_us / 2;
    status_led_set(on ? 1 : 0, 0, 0);
#endif
}

static void handle_alert(const mcu_frame_t *f)
{
    if (f->len < 3) {
        ESP_LOGW(TAG, "알림 프레임 길이 오류: %u", f->len);
        return;
    }
    uint16_t tag = (uint16_t)f->payload[0] | ((uint16_t)f->payload[1] << 8);
    uint8_t level = f->payload[2];
    const uint8_t b = LED_BRIGHTNESS;

    if (tag == MCU_SOLO_TAG_ID || !UWB_ENABLED) {
        /* 태그 대신 보드 LED. 색 LED: 1단계 노랑, 2단계 빨강 / 단색 LED: 1단계 느리게, 2단계 빠르게 깜빡임 */
        ESP_LOGI(TAG, "알림(보드 LED) level=%u", level);
        s_led_level = level;
        s_led_start_us = esp_timer_get_time();
        s_led_off_at_us = s_led_start_us + (int64_t)CONFIG_KKOT_ALERT_LED_MS * 1000;
        status_led_set(b, level >= 2 ? 0 : b, 0);
    } else {
        /* TODO: UWB/BLE로 해당 태그에 진동 명령 전달 */
        ESP_LOGI(TAG, "알림 tag=%04X level=%u (태그 전달 구현 예정)", tag, level);
    }
}

/* ---------- 태스크 ---------- */

static void power_task(void *arg)    { for (;;) { /* TODO: ADC 보정값으로 전압 측정 */ vTaskDelay(pdMS_TO_TICKS(5)); } }
static void watchdog_task(void *arg) { for (;;) { /* TODO: 하트비트 3초 무응답 시 재시작 */ vTaskDelay(pdMS_TO_TICKS(100)); } }

#if CONFIG_KKOT_UWB_ENABLE
static void uwb_task(void *arg)
{
    /* 1단계: SPI 배선·통신 확인. 칩을 찾을 때까지 주기적으로 DEV_ID를 읽는다. */
    if (uwb_spi_init() != ESP_OK) {
        ESP_LOGE(TAG, "UWB SPI 초기화 실패, uwb 태스크 중단");
        vTaskDelete(NULL);
    }
    for (;;) {
        uint32_t id = 0;
        uwb_spi_hard_reset();
        if (uwb_spi_read_dev_id(&id) == ESP_OK) {
            const char *name = uwb_dev_id_name(id);
            if (name) {
                ESP_LOGI(TAG, "UWB 칩 확인: DEV_ID=0x%08" PRIX32 " (%s)", id, name);
                break;
            }
            ESP_LOGW(TAG, "UWB 칩 응답 없음/알 수 없음: DEV_ID=0x%08" PRIX32 " (배선·전원 확인)", id);
        }
        vTaskDelay(pdMS_TO_TICKS(CONFIG_KKOT_UWB_PROBE_RETRY_MS));
    }
    for (;;) { /* TODO: UWB 드라이버 연동 (방향 측정) */ vTaskDelay(pdMS_TO_TICKS(50)); }
}
#endif

static void uart_task(void *arg)
{
    if (status_led_init() == ESP_OK) {
        /* 부팅 표시: 초록 0.3초. LED 핀 설정이 맞는지 눈으로 확인하는 용도 */
        status_led_set(0, LED_BRIGHTNESS, 0);
        vTaskDelay(pdMS_TO_TICKS(300));
        status_led_set(0, 0, 0);
    } else {
        ESP_LOGW(TAG, "상태 LED 초기화 실패");
    }
    if (link_init() != ESP_OK) {
        ESP_LOGE(TAG, "Jetson 연결 통로 초기화 실패, uart 태스크 중단");
        vTaskDelete(NULL);
    }

    mcu_frame_parser_t parser = { 0 };
    mcu_frame_t frame;
    uint8_t buf[64];
    for (;;) {
        int n = link_read(buf, sizeof(buf), pdMS_TO_TICKS(10));
        for (int i = 0; i < n; i++) {
            if (!mcu_frame_feed(&parser, buf[i], &frame)) {
                continue;
            }
            switch (frame.type) {
            case MCU_T_HEARTBEAT: s_last_heartbeat_us = esp_timer_get_time(); break;
            case MCU_T_ALERT:     handle_alert(&frame); break;
            default:              ESP_LOGW(TAG, "모르는 프레임 종류 0x%02X", frame.type); break;
            }
        }
        led_update(esp_timer_get_time());
    }
}

static void can_task(void *arg)      { for (;;) { /* TODO: TWAI 수신·송신 */ vTaskDelay(pdMS_TO_TICKS(10)); } }

void app_main(void)
{
    ESP_LOGI(TAG, "start");
#if !CONFIG_KKOT_UWB_ENABLE
    ESP_LOGW(TAG, "UWB 사용 안 함: 단독 테스트 빌드. 알림은 보드 LED로 표시 (운영 펌웨어 아님)");
#endif
    /* 안전 관련 태스크가 가장 높은 우선순위 */
    xTaskCreatePinnedToCore(power_task,    "power",    4096, NULL, 10, NULL, 1);
    xTaskCreatePinnedToCore(watchdog_task, "watchdog", 4096, NULL, 9,  NULL, 1);
#if CONFIG_KKOT_UWB_ENABLE
    xTaskCreatePinnedToCore(uwb_task,      "uwb",      6144, NULL, 8,  NULL, 0);
#endif
    xTaskCreatePinnedToCore(uart_task,     "uart",     4096, NULL, 7,  NULL, 0);
    xTaskCreatePinnedToCore(can_task,      "can",      4096, NULL, 6,  NULL, 0);
}
