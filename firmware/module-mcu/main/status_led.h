/*
 * 모듈 보드 상태 LED
 * - WS2812 RGB 1개 (RMT 사용): 색으로 단계 표시
 * - 단색 LED (GPIO): 켜고 끄기만 가능. 단계 구분은 호출하는 쪽에서 깜빡임 주기로 한다.
 * 종류와 핀은 Kconfig "KkotKkot status LED" 메뉴에서 정한다.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

esp_err_t status_led_init(void);

/* 단색 LED는 r·g·b 중 하나라도 0이 아니면 켠다 */
esp_err_t status_led_set(uint8_t r, uint8_t g, uint8_t b);

/* true면 색 표시가 가능한 LED(WS2812) */
bool status_led_has_color(void);
