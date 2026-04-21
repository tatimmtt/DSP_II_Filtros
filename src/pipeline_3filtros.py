"""
Pipeline completa: aplica os 3 filtros (FIR, IIR, Notch) em 2 sinais
  - audio-teste-ruido-G1.wav
  - ruido_branco.wav

Gera:
  - 6 áudios filtrados (.wav @ 48 kHz)
  - Gráficos FFT e espectrogramas antes/depois (3 filtros × 2 sinais)
  - Tabela comparativa de atenuação
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, fftfreq
import soundfile as sf
import librosa

FS = 48_000
F0_RUIDO = 874.98

AUDIO_G1 = '/mnt/user-data/uploads/audio-teste-ruido-G1.wav'
RUIDO_BRANCO = '/mnt/user-data/uploads/ruido_branco.wav'

os.makedirs('graficos', exist_ok=True)
os.makedirs('audio', exist_ok=True)

print("="*70)
print("  PIPELINE COMPLETA — 3 FILTROS × 2 SINAIS")
print("="*70)

# =========================================================================
# CARREGA OS COEFICIENTES
# =========================================================================
taps_fir = pd.read_csv('src/coeffs_FIR.csv', header=None).values[:, 0]
b_iir = np.load('src/coefs_iir_b.npy')
a_iir = np.load('src/coefs_iir_a.npy')
b_notch = np.load('src/coefs_notch_b.npy')
a_notch = np.load('src/coefs_notch_a.npy')

print("\n✓ Coeficientes carregados:")
print(f"  FIR:   {len(taps_fir)} taps")
print(f"  IIR:   {len(b_iir)} b, {len(a_iir)} a (Butterworth ordem 4)")
print(f"  Notch: {len(b_notch)} b, {len(a_notch)} a (Q=30)")

# =========================================================================
# FUNÇÕES AUXILIARES
# =========================================================================
def aplicar_filtros(x, fs):
    """Aplica os 3 filtros no sinal x. Retorna dict com 3 saídas."""
    # FIR: usa lfilter, compensa atraso
    atraso_fir = (len(taps_fir) - 1) // 2
    y_fir_raw = signal.lfilter(taps_fir, 1.0, x)
    y_fir = np.concatenate((y_fir_raw[atraso_fir:], np.zeros(atraso_fir)))
    
    # IIR: usa filtfilt para fase zero (ou lfilter se quiser comparar atraso)
    y_iir = signal.filtfilt(b_iir, a_iir, x)
    
    # Notch: usa filtfilt para fase zero
    y_notch = signal.filtfilt(b_notch, a_notch, x)
    
    return {'fir': y_fir, 'iir': y_iir, 'notch': y_notch}


def plot_fft_3filtros(x_in, filtrados, fs, titulo_base, fname):
    """Plota FFT: original + 3 filtrados lado a lado."""
    N = len(x_in)
    f = fftfreq(N, 1/fs)[:N//2]
    X_orig = 20*np.log10(np.abs(fft(x_in)[:N//2]) * 2/N + 1e-12)
    X_fir   = 20*np.log10(np.abs(fft(filtrados['fir'])[:N//2]) * 2/N + 1e-12)
    X_iir   = 20*np.log10(np.abs(fft(filtrados['iir'])[:N//2]) * 2/N + 1e-12)
    X_notch = 20*np.log10(np.abs(fft(filtrados['notch'])[:N//2]) * 2/N + 1e-12)
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    fig.suptitle(f'{titulo_base} — FFT antes/depois (3 filtros)', fontsize=13, fontweight='bold')
    
    dados = [
        (axes[0,0], X_orig, 'steelblue', 'Original'),
        (axes[0,1], X_fir, 'blue', 'FIR (N=199)'),
        (axes[1,0], X_iir, 'green', 'IIR Butterworth (ord 4)'),
        (axes[1,1], X_notch, 'red', 'Notch (Q=30)')
    ]
    
    for ax, X, cor, label in dados:
        ax.plot(f, X, cor, linewidth=0.6)
        ax.axvline(F0_RUIDO, color='orange', ls=':', alpha=0.8, linewidth=1)
        ax.set_xlim(0, 3000)
        ax.set_xlabel('Frequência (Hz)')
        ax.set_ylabel('Magnitude (dB)')
        ax.set_title(label, fontweight='bold')
        ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(fname, dpi=120, bbox_inches='tight')
    plt.close()


def plot_spec_3filtros(x_in, filtrados, fs, titulo_base, fname):
    """Espectrogramas: original + 3 filtrados."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    fig.suptitle(f'{titulo_base} — Espectrogramas (3 filtros)', fontsize=13, fontweight='bold')
    
    dados = [
        (axes[0,0], x_in, 'Original'),
        (axes[0,1], filtrados['fir'], 'FIR (N=199)'),
        (axes[1,0], filtrados['iir'], 'IIR Butterworth'),
        (axes[1,1], filtrados['notch'], 'Notch (Q=30)')
    ]
    
    for ax, x, label in dados:
        ax.specgram(x, NFFT=2048, Fs=fs, noverlap=1024, cmap='viridis')
        ax.set_ylim(0, 3000)
        ax.set_xlabel('Tempo (s)')
        ax.set_ylabel('Frequência (Hz)')
        ax.set_title(label, fontweight='bold')
        ax.axhline(F0_RUIDO, color='r', ls=':', alpha=0.8, linewidth=1)
    
    plt.tight_layout()
    plt.savefig(fname, dpi=120, bbox_inches='tight')
    plt.close()


def processar_audio(path_in, label, fs_alvo=FS):
    """Carrega, reamostra, filtra (3 filtros), salva wavs e gera plots."""
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    
    if not os.path.exists(path_in):
        print(f"  ⚠ Arquivo não encontrado: {path_in}")
        return None
    
    # Carrega e reamostra
    x_orig, fs_orig = librosa.load(path_in, sr=None, mono=True)
    print(f"  Entrada: {os.path.basename(path_in)}  Fs={fs_orig} Hz  {len(x_orig)/fs_orig:.2f} s")
    
    if fs_orig != fs_alvo:
        x = librosa.resample(x_orig, orig_sr=fs_orig, target_sr=fs_alvo)
        print(f"  Reamostrado: {fs_alvo} Hz ({len(x)} amostras)")
    else:
        x = x_orig
    
    # Aplica os 3 filtros
    filtrados = aplicar_filtros(x, fs_alvo)
    print(f"  Filtros aplicados: FIR, IIR, Notch")
    
    # Salva WAVs
    base_name = label.lower().replace(' ', '_').replace('-', '_')
    sf.write(f'audio/{base_name}_original_48k.wav', x.astype(np.float32), fs_alvo, subtype='PCM_16')
    sf.write(f'audio/{base_name}_fir_48k.wav', filtrados['fir'].astype(np.float32), fs_alvo, subtype='PCM_16')
    sf.write(f'audio/{base_name}_iir_48k.wav', filtrados['iir'].astype(np.float32), fs_alvo, subtype='PCM_16')
    sf.write(f'audio/{base_name}_notch_48k.wav', filtrados['notch'].astype(np.float32), fs_alvo, subtype='PCM_16')
    print(f"  Salvos: {base_name}_{{original,fir,iir,notch}}_48k.wav")
    
    # Gráficos
    plot_fft_3filtros(x, filtrados, fs_alvo, label, f'graficos/fft_{base_name}.png')
    plot_spec_3filtros(x, filtrados, fs_alvo, label, f'graficos/spec_{base_name}.png')
    print(f"  Gráficos: fft_{base_name}.png, spec_{base_name}.png")
    
    return x, filtrados


# =========================================================================
# PROCESSAMENTO DOS 2 SINAIS
# =========================================================================
r1 = processar_audio(AUDIO_G1, 'Áudio G1 (874.98 Hz)')
r2 = processar_audio(RUIDO_BRANCO, 'Ruído Branco (200 Hz - 20 kHz)')

# =========================================================================
# TABELA COMPARATIVA DE ATENUAÇÃO
# =========================================================================
print("\n" + "="*70)
print("  TABELA COMPARATIVA — Atenuação em f0 = 874.98 Hz")
print("="*70)

def medir_atenuacao(x_orig, x_filt, fs, f0):
    """Mede atenuação em f0 comparando FFT de x_orig e x_filt."""
    N = min(len(x_orig), len(x_filt))
    x_orig, x_filt = x_orig[:N], x_filt[:N]
    f = fftfreq(N, 1/fs)[:N//2]
    
    X_orig = np.abs(fft(x_orig)[:N//2]) * 2/N
    X_filt = np.abs(fft(x_filt)[:N//2]) * 2/N
    
    idx = np.argmin(np.abs(f - f0))
    
    mag_orig_dB = 20*np.log10(X_orig[idx] + 1e-12)
    mag_filt_dB = 20*np.log10(X_filt[idx] + 1e-12)
    
    atenuacao = mag_filt_dB - mag_orig_dB  # negativo = atenuou
    return atenuacao

if r1 is not None:
    x1, f1 = r1
    atten_g1 = {
        'FIR':   medir_atenuacao(x1, f1['fir'], FS, F0_RUIDO),
        'IIR':   medir_atenuacao(x1, f1['iir'], FS, F0_RUIDO),
        'Notch': medir_atenuacao(x1, f1['notch'], FS, F0_RUIDO)
    }
    print("\n  Áudio G1:")
    for nome, att in atten_g1.items():
        print(f"    {nome:<10} : {att:+.2f} dB")

if r2 is not None:
    x2, f2 = r2
    atten_rb = {
        'FIR':   medir_atenuacao(x2, f2['fir'], FS, F0_RUIDO),
        'IIR':   medir_atenuacao(x2, f2['iir'], FS, F0_RUIDO),
        'Notch': medir_atenuacao(x2, f2['notch'], FS, F0_RUIDO)
    }
    print("\n  Ruído Branco:")
    for nome, att in atten_rb.items():
        print(f"    {nome:<10} : {att:+.2f} dB")

print("\n" + "="*70)
print("  PIPELINE CONCLUÍDA")
print("="*70)
