"""
Pipeline completa de validação do filtro FIR rejeita-faixa em Python.

Aplica o filtro projetado em dois sinais de entrada:
  1) Áudio do projeto:          audio-teste-ruido-G1.wav  (44.1 kHz → resample 48 kHz)
  2) Ruído branco 200 Hz-20 kHz: gerado no OcenAudio pelo usuário

Gera:
  - Áudios filtrados (.wav)
  - FFT antes/depois
  - Espectrograma antes/depois
  - Resposta em frequência do filtro FIR projetado
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, fftfreq
import soundfile as sf
import librosa

# -------------------------------------------------------------------
# CONFIGURAÇÕES
# -------------------------------------------------------------------
FS_KIT    = 48_000                             # Taxa do codec Wolfson no STM32
NUMTAPS   = 199
F_CORTE   = [400, 1350]
JANELA    = 'hamming'
F_RUIDO   = 874.98                             # frequência do ruído dominante (identificada no notebook)

AUDIO_G1_IN    = '/mnt/user-data/uploads/audio-teste-ruido-G1.wav'
RUIDO_BRANCO_IN = '/mnt/user-data/uploads/ruido_branco.wav'  # anexado pelo usuário (OcenAudio)

PASTA_OUT = '.'
os.makedirs(os.path.join(PASTA_OUT, 'graficos'), exist_ok=True)

# -------------------------------------------------------------------
# 1) Re-carrega os coeficientes do CSV (exatamente como o professor faz)
# -------------------------------------------------------------------
taps = pd.read_csv('coeffs_FIR.csv', header=None).values[:, 0]
print(f"Filtro FIR carregado: {len(taps)} taps")

# -------------------------------------------------------------------
# 2) Resposta em frequência do filtro
# -------------------------------------------------------------------
w, h = signal.freqz(taps, [1], worN=8192, fs=FS_KIT)
mag_dB = 20 * np.log10(np.abs(h) + 1e-12)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7))
fig.suptitle('Resposta em frequência — FIR rejeita-faixa (N=199, Hamming, Fs=48 kHz)',
             fontsize=12, fontweight='bold')

ax1.plot(w, mag_dB, 'b', linewidth=1.2)
ax1.axvline(F_CORTE[0], color='k', ls='--', alpha=0.6, label=f'Fsb1 = {F_CORTE[0]} Hz')
ax1.axvline(F_CORTE[1], color='k', ls='--', alpha=0.6, label=f'Fsb2 = {F_CORTE[1]} Hz')
ax1.axvline(F_RUIDO, color='r', ls=':', alpha=0.8, label=f'Ruído = {F_RUIDO} Hz')
ax1.set_xlim(0, 3000)
ax1.set_ylim(-100, 5)
ax1.set_xlabel('Frequência (Hz)')
ax1.set_ylabel('Magnitude (dB)')
ax1.set_title('Zoom na banda de rejeição (0–3 kHz)')
ax1.grid(True, alpha=0.3)
ax1.legend(loc='lower right')

ax2.plot(w, mag_dB, 'b', linewidth=1.2)
ax2.axvline(F_CORTE[0], color='k', ls='--', alpha=0.6)
ax2.axvline(F_CORTE[1], color='k', ls='--', alpha=0.6)
ax2.axvline(F_RUIDO, color='r', ls=':', alpha=0.8)
ax2.set_xlim(0, FS_KIT / 2)
ax2.set_ylim(-100, 5)
ax2.set_xlabel('Frequência (Hz)')
ax2.set_ylabel('Magnitude (dB)')
ax2.set_title('Resposta completa (0 até Nyquist = 24 kHz)')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('graficos/01_resposta_em_frequencia_FIR.png', dpi=110)
plt.close()
print("-> graficos/01_resposta_em_frequencia_FIR.png")

# Atenuação na frequência do ruído
idx_ruido = np.argmin(np.abs(w - F_RUIDO))
print(f"   Atenuação em {F_RUIDO} Hz: {mag_dB[idx_ruido]:.2f} dB")

# -------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# -------------------------------------------------------------------
def aplicar_fir(sinal, coefs):
    """Convolução com compensação do atraso do FIR (filtro linear-phase)."""
    atraso = (len(coefs) - 1) // 2
    saida  = signal.lfilter(coefs, 1.0, sinal)
    # Alinha a saída compensando o atraso (para comparação visual)
    saida_alinhada = np.concatenate((saida[atraso:], np.zeros(atraso)))
    return saida, saida_alinhada


def plot_fft_antes_depois(x_in, x_out, fs, titulo, fname, xlim_hz=3000):
    """Plota FFT (dB) de entrada e saída lado a lado."""
    N_in  = len(x_in)
    N_out = len(x_out)
    f_in  = fftfreq(N_in, 1/fs)[:N_in//2]
    f_out = fftfreq(N_out, 1/fs)[:N_out//2]
    X_in  = 20*np.log10(np.abs(fft(x_in)[:N_in//2]) * 2/N_in + 1e-12)
    X_out = 20*np.log10(np.abs(fft(x_out)[:N_out//2]) * 2/N_out + 1e-12)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5))
    fig.suptitle(titulo, fontsize=12, fontweight='bold')

    ax1.plot(f_in, X_in, 'steelblue', linewidth=0.7)
    ax1.axvline(F_RUIDO, color='r', ls=':', alpha=0.7, label=f'{F_RUIDO} Hz')
    ax1.set_xlim(0, xlim_hz)
    ax1.set_xlabel('Frequência (Hz)')
    ax1.set_ylabel('Magnitude (dB)')
    ax1.set_title('ANTES do filtro')
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    ax2.plot(f_out, X_out, 'crimson', linewidth=0.7)
    ax2.axvline(F_RUIDO, color='r', ls=':', alpha=0.7, label=f'{F_RUIDO} Hz')
    ax2.set_xlim(0, xlim_hz)
    ax2.set_xlabel('Frequência (Hz)')
    ax2.set_ylabel('Magnitude (dB)')
    ax2.set_title('DEPOIS do filtro')
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    plt.tight_layout()
    plt.savefig(fname, dpi=110)
    plt.close()


def plot_spec_antes_depois(x_in, x_out, fs, titulo, fname):
    """Plota espectrogramas de entrada e saída."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5))
    fig.suptitle(titulo, fontsize=12, fontweight='bold')

    ax1.specgram(x_in,  NFFT=2048, Fs=fs, noverlap=1024, cmap='viridis')
    ax1.set_ylim(0, 3000)
    ax1.set_xlabel('Tempo (s)')
    ax1.set_ylabel('Frequência (Hz)')
    ax1.set_title('ANTES do filtro')
    ax1.axhline(F_RUIDO, color='r', ls=':', alpha=0.8, linewidth=1)

    ax2.specgram(x_out, NFFT=2048, Fs=fs, noverlap=1024, cmap='viridis')
    ax2.set_ylim(0, 3000)
    ax2.set_xlabel('Tempo (s)')
    ax2.set_ylabel('Frequência (Hz)')
    ax2.set_title('DEPOIS do filtro')
    ax2.axhline(F_RUIDO, color='r', ls=':', alpha=0.8, linewidth=1)

    plt.tight_layout()
    plt.savefig(fname, dpi=110)
    plt.close()


def processar_sinal(path_in, label, fname_out, fs_alvo=FS_KIT):
    """Carrega, reamostra (se preciso), filtra e salva .wav + plots."""
    print(f"\n{'='*60}\n  {label}\n{'='*60}")

    if not os.path.exists(path_in):
        print(f"  [AVISO] arquivo não encontrado: {path_in}")
        print(f"  Pulando processamento deste sinal.")
        return None

    # Carrega no sr original
    x_orig, fs_orig = librosa.load(path_in, sr=None, mono=True)
    print(f"  Entrada : {os.path.basename(path_in)}  |  Fs={fs_orig} Hz  |  {len(x_orig)/fs_orig:.2f} s")

    # Reamostra para 48 kHz (taxa do kit)
    if fs_orig != fs_alvo:
        x = librosa.resample(x_orig, orig_sr=fs_orig, target_sr=fs_alvo)
        print(f"  Reamostrado para {fs_alvo} Hz  ({len(x)} amostras)")
    else:
        x = x_orig

    # Aplica o filtro
    y_raw, y_aligned = aplicar_fir(x, taps)
    print(f"  Filtrado. Atraso do FIR: {(len(taps)-1)//2} amostras "
          f"({(len(taps)-1)/2/fs_alvo*1000:.2f} ms)")

    # Salva áudios (original resamplado + filtrado)
    orig_out = f'{fname_out}_original_48k.wav'
    filt_out = f'{fname_out}_filtrado_48k.wav'
    sf.write(orig_out, x.astype(np.float32), fs_alvo, subtype='PCM_16')
    sf.write(filt_out, y_aligned.astype(np.float32), fs_alvo, subtype='PCM_16')
    print(f"  -> {orig_out}")
    print(f"  -> {filt_out}")

    # Plots
    plot_fft_antes_depois(x, y_aligned, fs_alvo,
                          f'FFT antes/depois do filtro — {label}',
                          f'graficos/fft_{fname_out}.png',
                          xlim_hz=3000)
    plot_spec_antes_depois(x, y_aligned, fs_alvo,
                           f'Espectrograma antes/depois — {label}',
                           f'graficos/spec_{fname_out}.png')
    print(f"  -> graficos/fft_{fname_out}.png")
    print(f"  -> graficos/spec_{fname_out}.png")

    return x, y_aligned


# -------------------------------------------------------------------
# 3) PROCESSAMENTO DOS DOIS SINAIS
# -------------------------------------------------------------------
r1 = processar_sinal(AUDIO_G1_IN,       'Áudio audio-teste-ruido-G1',  'audio_G1')
r2 = processar_sinal(RUIDO_BRANCO_IN,   'Ruído branco 200 Hz – 20 kHz', 'ruido_branco')

print("\n" + "="*60)
print("  Pipeline concluída.")
print("="*60)
