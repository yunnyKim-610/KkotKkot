/*
 * 꼿꼿 센싱 모듈 보조 MCU (ESP32-S3, ESP-IDF) - 뼈대
 *
 * 태스크 구성 (FreeRTOS)
 *  - power_task    : 입력 전압 감시(ADC), 저하 시 Jetson에 종료 요청 GPIO
 *  - watchdog_task : Jetson 하트비트 확인, 끊기면 Jetson 재시작 GPIO
 *  - uwb_task      : UWB 방향 측정 칩(SPI) 처리
 *  - uart_task     : Jetson과 UART 프레임 송수신
 *  - can_task      : 로봇 본체와 TWAI(CAN) 통신
 *
 * 원칙: Wi-Fi/BLE 무선은 사용하지 않는다 (Jetson이 담당). 안전 기능이 무선 스택에 영향받지 않게 한다.
 */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "kkotkkot-mcu";

static void power_task(void *arg)    { for (;;) { /* TODO: ADC 보정값으로 전압 측정 */ vTaskDelay(pdMS_TO_TICKS(5)); } }
static void watchdog_task(void *arg) { for (;;) { /* TODO: 하트비트 3초 무응답 시 재시작 */ vTaskDelay(pdMS_TO_TICKS(100)); } }
static void uwb_task(void *arg)      { for (;;) { /* TODO: UWB 드라이버 연동 */ vTaskDelay(pdMS_TO_TICKS(50)); } }
static void uart_task(void *arg)     { for (;;) { /* TODO: [0xAA][type][len][payload][crc16] */ vTaskDelay(pdMS_TO_TICKS(10)); } }
static void can_task(void *arg)      { for (;;) { /* TODO: TWAI 수신·송신 */ vTaskDelay(pdMS_TO_TICKS(10)); } }

void app_main(void)
{
    ESP_LOGI(TAG, "start");
    /* 안전 관련 태스크가 가장 높은 우선순위 */
    xTaskCreatePinnedToCore(power_task,    "power",    4096, NULL, 10, NULL, 1);
    xTaskCreatePinnedToCore(watchdog_task, "watchdog", 4096, NULL, 9,  NULL, 1);
    xTaskCreatePinnedToCore(uwb_task,      "uwb",      6144, NULL, 8,  NULL, 0);
    xTaskCreatePinnedToCore(uart_task,     "uart",     4096, NULL, 7,  NULL, 0);
    xTaskCreatePinnedToCore(can_task,      "can",      4096, NULL, 6,  NULL, 0);
}
