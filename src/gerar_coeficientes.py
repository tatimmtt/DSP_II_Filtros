"""
Gera os coeficientes do filtro FIR rejeita-faixa com as specs validadas
no projeto e produz:
  - coeffs_FIR.csv  (formato vertical, igual ao exportado pelo pyfda)
  - coeffs_FIR.h    (header CMSIS-DSP para embarcar no STM32)

Specs do projeto (notebook):
  Fs      = 48 kHz   (taxa do kit Wolfson/STM32)
  N       = 199      (numtaps, ordem 198)
  Fsb1    = 400  Hz  (início da banda de rejeição)
  Fsb2    = 1350 Hz  (fim da banda de rejeição)
  Janela  = Hamming
  Tipo    = rejeita-faixa (bandstop)
  Centro  ≈ 874.98 Hz (frequência do ruído dominante)
"""

import numpy as np
import pandas as pd
from scipy import signal

# -------------------------------------------------------------------
# 1) Projeto do filtro FIR — equivalente ao pyfda com janela Hamming
# -------------------------------------------------------------------
FS       = 48_000
NUMTAPS  = 199
F_CORTE  = [400, 1350]
JANELA   = 'hamming'

taps = signal.firwin(NUMTAPS, F_CORTE,
                     pass_zero='bandstop',
                     window=JANELA,
                     fs=FS)

print(f"Coeficientes gerados: {len(taps)} taps")
print(f"  Soma dos coeficientes : {taps.sum():.6f}   (referência: próximo de 1 fora da banda)")
print(f"  Max |h[n]|            : {np.max(np.abs(taps)):.6f}")

# -------------------------------------------------------------------
# 2) Exporta CSV no mesmo formato que o pyfda exporta (Table Orientation = Vertical)
#    -> uma coluna, sem header, um coeficiente por linha
# -------------------------------------------------------------------
df = pd.DataFrame(taps)
df.to_csv('coeffs_FIR.csv', header=False, index=False)
print("-> coeffs_FIR.csv gerado (vertical, sem header).")

# -------------------------------------------------------------------
# 3) Gera o coeffs_FIR.h usando a função do script do professor
#    (reproduzida aqui para manter o pipeline reprodutível)
# -------------------------------------------------------------------
def fir_header(fname_out, val):
    """Reproduz Le_CSV_Pyfda_gera_coeff_FIR.py::fir_header()"""
    Ns = len(val)
    if (Ns % 2) != 0:
        val = np.append(val, 0)
        Ns = len(val)
    val_fixo = np.round(val * 2**15)

    with open(fname_out, 'wt') as f:
        f.write('//define a FIR CMSIS-DSP coefficient array\n\n')
        f.write('#ifndef INCLUDE_COEFFS_FIR_H_\n')
        f.write('#define INCLUDE_COEFFS_FIR_H_\n\n')
        f.write('#include <stdint.h>\n\n')
        f.write('#include "filter.h"\n\n')
        f.write('#ifndef NUM_TAPS\n')
        f.write('#define NUM_TAPS %d\n' % Ns)
        f.write('#endif\n\n')
        f.write('/*************************************/\n')
        f.write('/*     FIR Filter Coefficients       */\n')
        f.write('const float32_t firCoeffs32[%d] = { ' % Ns)
        for k in range(Ns):
            if (k < Ns - 1):
                f.write(' %+-13e, ' % val[k])
            else:
                f.write(' %+-13e ' % val[k])
        f.write('};\n\n')
        f.write('const q15_t firCoeffsQ15[%d] = { ' % Ns)
        for k in range(Ns):
            if (k < Ns - 1):
                f.write(' %d, ' % val_fixo[k])
            else:
                f.write(' %d ' % val_fixo[k])
        f.write('};\n')
        f.write('FilterTypeDef filterType=FIR_FLOAT32;\n')
        f.write('/***********************************/\n\n')
        f.write('#endif /* INCLUDE_COEFFS_FIR_H_ */')


# Lê o CSV (mesmo fluxo do script original) e gera o .h
dados = pd.read_csv('coeffs_FIR.csv', header=None)
valores = dados.values[:, 0]
fir_header('coeffs_FIR.h', valores)
print("-> coeffs_FIR.h gerado (CMSIS-DSP).")

# -------------------------------------------------------------------
# 4) Sanity check: após fir_header, NUM_TAPS ficou par?
# -------------------------------------------------------------------
num_taps_final = len(valores) + (1 if (len(valores) % 2) else 0)
print(f"\nNUM_TAPS gravado no .h: {num_taps_final} (o CMSIS-DSP exige par e >4)")
