"""
Gera os coeficientes dos 3 filtros e seus headers CMSIS-DSP:
  1. FIR:   N=199, Hamming, bandstop 400-1350 Hz (já validado)
  2. IIR:   Butterworth, ordem 4, bandstop 400-1350 Hz, float32
  3. NOTCH: 2ª ordem, Q=30, f0=874.98 Hz, BW≈29 Hz, float32
"""

import numpy as np
import pandas as pd
from scipy import signal
import matplotlib.pyplot as plt

FS = 48_000
F0_RUIDO = 874.98

print("="*70)
print("  GERAÇÃO DOS COEFICIENTES - 3 FILTROS")
print("="*70)

# =========================================================================
# 1) FILTRO FIR — Hamming, N=199, bandstop 400-1350 Hz
# =========================================================================
print("\n[1/3] FIR (Hamming, N=199, bandstop 400-1350 Hz)")
NUMTAPS_FIR = 199
F_CORTE_FIR = [400, 1350]
taps_fir = signal.firwin(NUMTAPS_FIR, F_CORTE_FIR,
                         pass_zero='bandstop',
                         window='hamming',
                         fs=FS)
# Exporta CSV
pd.DataFrame(taps_fir).to_csv('src/coeffs_FIR.csv', header=False, index=False)
print(f"  ✓ {len(taps_fir)} taps gerados → src/coeffs_FIR.csv")

# =========================================================================
# 2) FILTRO IIR — Butterworth 4ª ordem, bandstop 400-1350 Hz
# =========================================================================
print("\n[2/3] IIR Butterworth (ordem 4, bandstop 400-1350 Hz)")
ORDEM_IIR = 4
F_CORTE_IIR = [400, 1350]
sos_iir = signal.butter(ORDEM_IIR, F_CORTE_IIR,
                        btype='bandstop',
                        fs=FS,
                        output='sos')  # Second-Order Sections (mais estável)
# Converte SOS para coeficientes b,a (single-section para CMSIS-DSP)
b_iir, a_iir = signal.sos2tf(sos_iir)
print(f"  ✓ Ordem {ORDEM_IIR} → {len(b_iir)} coefs b, {len(a_iir)} coefs a")
print(f"    b = {b_iir[:5]}... (primeiros 5)")
print(f"    a = {a_iir[:5]}... (primeiros 5)")

# =========================================================================
# 3) FILTRO NOTCH — 2ª ordem, Q=30, f0=874.98 Hz
# =========================================================================
print("\n[3/3] Notch (2ª ordem, Q=30, f0={:.2f} Hz, BW≈29 Hz)".format(F0_RUIDO))
Q_NOTCH = 30.0
b_notch, a_notch = signal.iirnotch(F0_RUIDO, Q_NOTCH, FS)
print(f"  ✓ 3 coefs b, 3 coefs a")
print(f"    b = {b_notch}")
print(f"    a = {a_notch}")

# =========================================================================
# FUNÇÃO: Gera header CMSIS-DSP para FIR (igual ao script anterior)
# =========================================================================
def fir_header(fname_out, val):
    Ns = len(val)
    if (Ns % 2) != 0:
        val = np.append(val, 0)
        Ns = len(val)
    val_fixo = np.round(val * 2**15)

    with open(fname_out, 'wt') as f:
        f.write('// FIR CMSIS-DSP coefficient array\n\n')
        f.write('#ifndef INCLUDE_COEFFS_FIR_H_\n')
        f.write('#define INCLUDE_COEFFS_FIR_H_\n\n')
        f.write('#include <stdint.h>\n')
        f.write('#include "arm_math.h"\n\n')
        f.write('#ifndef NUM_TAPS_FIR\n')
        f.write(f'#define NUM_TAPS_FIR {Ns}\n')
        f.write('#endif\n\n')
        f.write('const float32_t firCoeffs32[NUM_TAPS_FIR] = { ')
        for k in range(Ns):
            sep = ', ' if k < Ns - 1 else ' '
            f.write(f'{val[k]:+.10e}{sep}')
        f.write('};\n\n')
        f.write('#endif /* INCLUDE_COEFFS_FIR_H_ */\n')

# =========================================================================
# FUNÇÃO: Gera header CMSIS-DSP para IIR (biquad ou direct-form)
# =========================================================================
def iir_header(fname_out, b, a):
    """
    Gera header para IIR usando CMSIS-DSP arm_biquad_cascade_df1_f32.
    Converte coefs (b,a) em cascata de biquads (Second-Order Sections).
    """
    # CMSIS-DSP espera SOS: cada seção tem [b0, b1, b2, a1, a2]
    # (note que a0 é normalizado para 1, então não aparece)
    
    # Para um Butterworth de ordem 4, teremos 2 biquads (4/2=2 seções)
    # Vamos usar o sos original que já está nesse formato
    sos = signal.butter(ORDEM_IIR, F_CORTE_IIR, btype='bandstop', fs=FS, output='sos')
    num_stages = sos.shape[0]  # número de seções biquad
    
    # Reorganiza coefs no formato CMSIS-DSP: [b0, b1, b2, a1, a2] por seção
    coefs_cmsis = []
    for stage in sos:
        b0, b1, b2, a0, a1, a2 = stage
        # CMSIS-DSP assume a0=1, então divide tudo por a0 se necessário
        if a0 != 1.0:
            b0, b1, b2 = b0/a0, b1/a0, b2/a0
            a1, a2 = a1/a0, a2/a0
        coefs_cmsis.extend([b0, b1, b2, -a1, -a2])  # CMSIS usa -a1, -a2
    
    with open(fname_out, 'wt') as f:
        f.write('// IIR Butterworth Biquad Cascade (CMSIS-DSP)\n\n')
        f.write('#ifndef INCLUDE_COEFFS_IIR_H_\n')
        f.write('#define INCLUDE_COEFFS_IIR_H_\n\n')
        f.write('#include <stdint.h>\n')
        f.write('#include "arm_math.h"\n\n')
        f.write(f'#define NUM_STAGES_IIR {num_stages}\n\n')
        f.write(f'// {num_stages} biquad stages × 5 coefs = {len(coefs_cmsis)} total\n')
        f.write(f'const float32_t iirCoeffs32[{len(coefs_cmsis)}] = {{\n')
        for i, c in enumerate(coefs_cmsis):
            sep = ',\n' if (i+1) % 5 == 0 and i < len(coefs_cmsis)-1 else ', '
            if i == len(coefs_cmsis)-1:
                sep = ''
            f.write(f'  {c:+.10e}{sep}')
        f.write('\n};\n\n')
        f.write('// State buffer: 4 × NUM_STAGES (d1, d2 para cada biquad)\n')
        f.write(f'// float32_t iirState[{4*num_stages}];  // declare no main\n\n')
        f.write('#endif /* INCLUDE_COEFFS_IIR_H_ */\n')

# =========================================================================
# FUNÇÃO: Gera header CMSIS-DSP para NOTCH (1 biquad)
# =========================================================================
def notch_header(fname_out, b, a):
    """Notch é 1 biquad apenas (2ª ordem)."""
    # Normaliza por a[0]
    b0, b1, b2 = b / a[0]
    a1_n, a2_n = a[1] / a[0], a[2] / a[0]
    
    coefs = [b0, b1, b2, -a1_n, -a2_n]  # CMSIS usa -a1, -a2
    
    with open(fname_out, 'wt') as f:
        f.write('// Notch Filter (2nd order biquad, Q=30)\n\n')
        f.write('#ifndef INCLUDE_COEFFS_NOTCH_H_\n')
        f.write('#define INCLUDE_COEFFS_NOTCH_H_\n\n')
        f.write('#include <stdint.h>\n')
        f.write('#include "arm_math.h"\n\n')
        f.write('#define NUM_STAGES_NOTCH 1\n\n')
        f.write('const float32_t notchCoeffs32[5] = {\n')
        for i, c in enumerate(coefs):
            sep = ',\n' if i < 4 else '\n'
            f.write(f'  {c:+.10e}{sep}')
        f.write('};\n\n')
        f.write('// State buffer: float32_t notchState[4]; (declare no main)\n\n')
        f.write('#endif /* INCLUDE_COEFFS_NOTCH_H_ */\n')

# =========================================================================
# GERA OS 3 HEADERS
# =========================================================================
fir_header('src/coeffs_FIR.h', taps_fir)
iir_header('src/coeffs_IIR.h', b_iir, a_iir)
notch_header('src/coeffs_NOTCH.h', b_notch, a_notch)

print("\n" + "="*70)
print("  HEADERS GERADOS")
print("="*70)
print("  ✓ src/coeffs_FIR.h")
print("  ✓ src/coeffs_IIR.h")
print("  ✓ src/coeffs_NOTCH.h")

# =========================================================================
# SALVA COEFS IIR E NOTCH TAMBÉM EM .NPY PARA O PIPELINE PYTHON
# =========================================================================
np.save('src/coefs_iir_b.npy', b_iir)
np.save('src/coefs_iir_a.npy', a_iir)
np.save('src/coefs_notch_b.npy', b_notch)
np.save('src/coefs_notch_a.npy', a_notch)
print("\n  ✓ Coeficientes salvos em .npy para pipeline Python")

# =========================================================================
# PLOTA RESPOSTAS EM FREQUÊNCIA DOS 3 FILTROS (COMPARAÇÃO)
# =========================================================================
w_fir, h_fir = signal.freqz(taps_fir, [1], worN=8192, fs=FS)
w_iir, h_iir = signal.freqz(b_iir, a_iir, worN=8192, fs=FS)
w_notch, h_notch = signal.freqz(b_notch, a_notch, worN=8192, fs=FS)

mag_fir_dB = 20*np.log10(np.abs(h_fir) + 1e-12)
mag_iir_dB = 20*np.log10(np.abs(h_iir) + 1e-12)
mag_notch_dB = 20*np.log10(np.abs(h_notch) + 1e-12)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
fig.suptitle('Comparação: Resposta em Frequência dos 3 Filtros', fontsize=13, fontweight='bold')

# Zoom na banda de rejeição
for ax, xlim, titulo in [(ax1, (0, 3000), 'Zoom na banda de rejeição (0-3 kHz)'),
                          (ax2, (0, FS/2), f'Resposta completa (0-{FS//2} Hz)')]:
    ax.plot(w_fir, mag_fir_dB, 'b', linewidth=1.2, label='FIR (N=199, Hamming)', alpha=0.7)
    ax.plot(w_iir, mag_iir_dB, 'g', linewidth=1.2, label='IIR Butterworth (ord 4)', alpha=0.7)
    ax.plot(w_notch, mag_notch_dB, 'r', linewidth=1.5, label='Notch (Q=30)', alpha=0.9)
    ax.axvline(F0_RUIDO, color='orange', ls=':', alpha=0.8, label=f'f0 = {F0_RUIDO} Hz')
    ax.set_xlim(xlim)
    ax.set_ylim(-120, 5)
    ax.set_xlabel('Frequência (Hz)')
    ax.set_ylabel('Magnitude (dB)')
    ax.set_title(titulo)
    ax.grid(True, alpha=0.3)
    if ax is ax1:
        ax.legend(loc='lower right')

plt.tight_layout()
plt.savefig('graficos/00_comparacao_3filtros_freq_response.png', dpi=120, bbox_inches='tight')
plt.close()
print("  ✓ graficos/00_comparacao_3filtros_freq_response.png")

# Atenuação em f0
idx_fir = np.argmin(np.abs(w_fir - F0_RUIDO))
idx_iir = np.argmin(np.abs(w_iir - F0_RUIDO))
idx_notch = np.argmin(np.abs(w_notch - F0_RUIDO))

print("\n" + "="*70)
print(f"  ATENUAÇÃO EM f0 = {F0_RUIDO} Hz")
print("="*70)
print(f"  FIR (N=199)         : {mag_fir_dB[idx_fir]:.2f} dB")
print(f"  IIR Butterworth (4) : {mag_iir_dB[idx_iir]:.2f} dB")
print(f"  Notch (Q=30)        : {mag_notch_dB[idx_notch]:.2f} dB")
print("="*70)
