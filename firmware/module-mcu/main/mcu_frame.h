/*
 * Jetson ↔ MCU 프레임 (module/shared/mcu_frame.py 와 같은 규칙)
 *
 * [0xAA][type 1B][len 1B][payload len B][crc16 2B, 리틀 엔디언]
 * CRC-16/CCITT-FALSE (다항식 0x1021, 초기값 0xFFFF), 범위는 type·len·payload.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define MCU_FRAME_SOF          0xAA
#define MCU_FRAME_MAX_PAYLOAD  64

#define MCU_T_UWB           0x01
#define MCU_T_IMU           0x02
#define MCU_T_POWER         0x03
#define MCU_T_ALERT         0x10   /* tag_id u16 LE, level u8 */
#define MCU_T_CAMERA_POWER  0x11
#define MCU_T_HEARTBEAT     0x12

#define MCU_SOLO_TAG_ID     0x0000 /* 예약: 태그 대신 모듈 보드 LED로 알림 (단독 테스트) */

typedef struct {
    uint8_t type;
    uint8_t len;
    uint8_t payload[MCU_FRAME_MAX_PAYLOAD];
} mcu_frame_t;

typedef struct {
    uint8_t buf[3 + MCU_FRAME_MAX_PAYLOAD + 2];
    size_t n;
} mcu_frame_parser_t;

uint16_t mcu_crc16(const uint8_t *data, size_t len);

/* 바이트 하나를 넣는다. 프레임이 완성되고 CRC가 맞으면 out에 채우고 true. */
bool mcu_frame_feed(mcu_frame_parser_t *p, uint8_t byte, mcu_frame_t *out);
