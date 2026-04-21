// Notch Filter (2nd order biquad, Q=30)

#ifndef INCLUDE_COEFFS_NOTCH_H_
#define INCLUDE_COEFFS_NOTCH_H_

#include <stdint.h>
#include "arm_math.h"

#define NUM_STAGES_NOTCH 1

const float32_t notchCoeffs32[5] = {
  +9.9809472445e-01,
  -1.9831105718e+00,
  +9.9809472445e-01,
  +1.9831105718e+00,
  -9.9618944890e-01
};

// State buffer: float32_t notchState[4]; (declare no main)

#endif /* INCLUDE_COEFFS_NOTCH_H_ */
