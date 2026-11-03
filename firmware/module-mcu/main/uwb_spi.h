/*
 * UWB 칩(Qorvo DW3000 계열) SPI 연결 확인
 *
 * 드라이버 이식 전에 SPI 배선과 통신이 되는지부터 확인하는 최소 코드다.
 * DEV_ID 레지스터(0x00:00)를 읽어 칩 종류를 판별한다.
 */
#pragma once

#include <stdint.h>
#include "esp_err.h"

/* SPI 버스와 칩 리셋 핀을 초기화한다. 핀 번호는 menuconfig(Kconfig.projbuild)에서 정한다. */
esp_err_t uwb_spi_init(void);

/* RSTn 핀으로 칩을 하드웨어 리셋한다. 리셋 핀을 쓰지 않으면(-1) 아무것도 하지 않는다. */
void uwb_spi_hard_reset(void);

/* DEV_ID 레지스터를 읽는다. */
esp_err_t uwb_spi_read_dev_id(uint32_t *dev_id);

/* DEV_ID 값을 사람이 읽을 이름으로 바꾼다. 모르는 값이면 NULL. */
const char *uwb_dev_id_name(uint32_t dev_id);
