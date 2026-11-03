/*
 * Jetson ↔ MCU 프레임 파서
 * 깨진 프레임은 버리고 버퍼 안의 다음 SOF부터 다시 찾는다 (Python FrameParser 와 같은 동작).
 */
#include "mcu_frame.h"

#include <string.h>

uint16_t mcu_crc16(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int b = 0; b < 8; b++) {
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

/* 버퍼 앞의 1바이트를 버리고 다음 SOF 위치로 당긴다 */
static void resync(mcu_frame_parser_t *p)
{
    size_t i = 1;
    while (i < p->n && p->buf[i] != MCU_FRAME_SOF) {
        i++;
    }
    memmove(p->buf, p->buf + i, p->n - i);
    p->n -= i;
}

bool mcu_frame_feed(mcu_frame_parser_t *p, uint8_t byte, mcu_frame_t *out)
{
    if (p->n == 0 && byte != MCU_FRAME_SOF) {
        return false;
    }
    p->buf[p->n++] = byte;

    for (;;) {
        if (p->n < 3) {
            return false;
        }
        uint8_t len = p->buf[2];
        if (len > MCU_FRAME_MAX_PAYLOAD) {
            resync(p);
            continue;
        }
        size_t total = 3 + (size_t)len + 2;
        if (p->n < total) {
            return false;
        }
        uint16_t crc = (uint16_t)p->buf[3 + len] | ((uint16_t)p->buf[4 + len] << 8);
        if (crc == mcu_crc16(&p->buf[1], 2 + (size_t)len)) {
            out->type = p->buf[1];
            out->len = len;
            memcpy(out->payload, &p->buf[3], len);
            p->n = 0;   /* 바이트 단위로 넣으므로 완성 시점에 남는 바이트는 없다 */
            return true;
        }
        resync(p);
    }
}
