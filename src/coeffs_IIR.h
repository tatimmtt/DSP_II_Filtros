// IIR Butterworth Biquad Cascade (CMSIS-DSP)

#ifndef INCLUDE_COEFFS_IIR_H_
#define INCLUDE_COEFFS_IIR_H_

#include <stdint.h>
#include "arm_math.h"

#define NUM_STAGES_IIR 4

// 4 biquad stages × 5 coefs = 20 total
const float32_t iirCoeffs32[20] = {
  +8.4993100875e-01,   -1.6919937361e+00,   +8.4993100875e-01,   +1.8465299770e+00,   -8.6214422145e-01,
  +1.0000000000e+00,   -1.9907424469e+00,   +1.0000000000e+00,   +1.9164916355e+00,   -9.2139704309e-01,
  +1.0000000000e+00,   -1.9907424469e+00,   +1.0000000000e+00,   +1.9020215330e+00,   -9.3034524802e-01,
  +1.0000000000e+00,   -1.9907424469e+00,   +1.0000000000e+00,   +1.9745767713e+00,   -9.7745431700e-01
};

// State buffer: 4 × NUM_STAGES (d1, d2 para cada biquad)
// float32_t iirState[16];  // declare no main

#endif /* INCLUDE_COEFFS_IIR_H_ */
