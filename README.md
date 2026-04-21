# Relatório Técnico — 3 Filtros Digitais Rejeita-Faixa

**Disciplina:** DSP II  
**Aluno:** Mateus F. Tatim  
**Data:** Abril/2026

---

## 📋 Resumo Executivo

Este projeto implementa e compara **3 filtros digitais** para supressão de ruído tonal
em 874,98 Hz:

| Filtro | Atenuação @ 874,98 Hz | Banda de Rejeição | Complexidade |
|--------|----------------------|-------------------|--------------|
| **FIR (Hamming, N=199)** | -48,6 dB | 950 Hz | 200 coeficientes |
| **IIR Butterworth (4ª ordem)** | -90+ dB | 950 Hz | 10 coeficientes |
| **Notch (Q=30)** | **-104 dB** | **29 Hz** | **5 coeficientes** |

**Vencedor:** Filtro **Notch** — atenuação cirúrgica com complexidade mínima.

---

## 📁 Estrutura do Projeto

```
relatorio_completo/
├── relatorio_DSP_II_3filtros.ipynb    ← RELATÓRIO PRINCIPAL (.ipynb)
├── relatorio_DSP_II_3filtros.html     ← HTML (visualizar no browser)
│
├── src/                               ← Código e headers STM32
│   ├── coeffs_FIR.h                  # Header CMSIS-DSP (FIR)
│   ├── coeffs_FIR.csv
│   ├── coeffs_IIR.h                  # Header CMSIS-DSP (IIR Butterworth)
│   ├── coeffs_NOTCH.h                # Header CMSIS-DSP (Notch Q=30)
│   ├── coefs_iir_b.npy               # Coefs Python (IIR)
│   ├── coefs_iir_a.npy
│   ├── coefs_notch_b.npy             # Coefs Python (Notch)
│   ├── coefs_notch_a.npy
│   ├── gerar_todos_coeficientes.py   # Gera os 3 filtros
│   └── pipeline_3filtros.py          # Aplica nos 2 sinais
│
├── audio/                             ← Áudios processados (48 kHz)
│   ├── audio_g1_original_48k.wav
│   ├── audio_g1_fir_48k.wav          # G1 filtrado com FIR
│   ├── audio_g1_iir_48k.wav          # G1 filtrado com IIR
│   ├── audio_g1_notch_48k.wav        # G1 filtrado com Notch
│   ├── ruido_branco_original_48k.wav
│   ├── ruido_branco_fir_48k.wav
│   ├── ruido_branco_iir_48k.wav
│   └── ruido_branco_notch_48k.wav
│
└── graficos/                          ← Visualizações (FFT, espectrogramas)
    ├── 00_comparacao_3filtros_freq_response.png
    ├── fft_audio_g1.png
    ├── fft_ruido_branco.png
    ├── spec_audio_g1.png
    └── spec_ruido_branco.png
```

---

## 🚀 Como Visualizar o Relatório

### Opção 1: HTML (recomendado)
```bash
# Abra no navegador:
relatorio_DSP_II_3filtros.html
```

### Opção 2: Jupyter Notebook
```bash
jupyter notebook relatorio_DSP_II_3filtros.ipynb
```

### Opção 3: Rodar a pipeline Python

```bash
# Gera os coeficientes dos 3 filtros
python src/gerar_todos_coeficientes.py

# Aplica nos 2 sinais e gera gráficos
python src/pipeline_3filtros.py
```

---

## 🔧 Implementação no STM32F4

### Headers gerados (CMSIS-DSP float32):

1. **`src/coeffs_FIR.h`** — 200 taps (FIR Hamming)
2. **`src/coeffs_IIR.h`** — 2 biquads em cascata (Butterworth)
3. **`src/coeffs_NOTCH.h`** — 1 biquad (Notch Q=30)

### Exemplo de uso no `main.c`:

```c
#include "coeffs_FIR.h"
#include "coeffs_IIR.h"
#include "coeffs_NOTCH.h"

// Escolha 1 dos 3 filtros:

// --- OPÇÃO 1: FIR ---
arm_fir_instance_f32 S;
float32_t firState[BLOCK_SIZE + NUM_TAPS_FIR - 1];
arm_fir_init_f32(&S, NUM_TAPS_FIR, firCoeffs32, firState, BLOCK_SIZE);
// No loop:
arm_fir_f32(&S, inputF32, outputF32, BLOCK_SIZE);

// --- OPÇÃO 2: IIR Butterworth ---
arm_biquad_casd_df1_inst_f32 S_iir;
float32_t iirState[4 * NUM_STAGES_IIR];  // 4 × 2 = 8
arm_biquad_cascade_df1_init_f32(&S_iir, NUM_STAGES_IIR, iirCoeffs32, iirState);
// No loop:
arm_biquad_cascade_df1_f32(&S_iir, inputF32, outputF32, BLOCK_SIZE);

// --- OPÇÃO 3: Notch ---
arm_biquad_casd_df1_inst_f32 S_notch;
float32_t notchState[4];
arm_biquad_cascade_df1_init_f32(&S_notch, 1, notchCoeffs32, notchState);
// No loop:
arm_biquad_cascade_df1_f32(&S_notch, inputF32, outputF32, BLOCK_SIZE);
```

### Fluxo de teste:

1. PC → cabo P2 → LINE-IN do Wolfson Pi Audio
2. STM32 processa em tempo real (DMA, 128 amostras/bloco)
3. Saída: fone ou LINE-OUT
4. Capture e compare com `.wav` de referência em `audio/`

---

## 📊 Resultados Principais

### Tabela Comparativa — Atenuação Medida

| Filtro | Áudio G1 | Ruído Branco |
|--------|----------|--------------|
| **FIR (N=199)** | -48,64 dB | -48,62 dB |
| **IIR Butterworth** | -92,63 dB | -90,90 dB |
| **Notch (Q=30)** | -66,76 dB | **-104,27 dB** |

### Interpretação:

- **FIR:** Banda larga (950 Hz) → atenuação moderada, afeta faixa de voz
- **IIR:** Atenuação excelente (-90 dB), mas banda ainda larga
- **Notch:** Atenuação cirúrgica (-104 dB), preserva 99,7% do espectro

---

## 🏆 Conclusão

**Para ruído tonal puro em frequência conhecida: use Notch.**

- **3× melhor atenuação** que o FIR (-104 dB vs -48 dB)
- **32× mais seletivo** (29 Hz vs 950 Hz)
- **40× menos complexo** (5 vs 200 coeficientes)

**Trade-offs:**
- FIR: fase linear (crítico em áudio profissional)
- IIR: melhor atenuação/ordem, mas fase não-linear
- Notch: ideal para este projeto, mas sensível a desvios de ±5 Hz em f₀

---

## 📚 Dependências Python

```bash
pip install numpy scipy matplotlib pandas soundfile librosa
```

---

## 📞 Contato

**Mateus F. Tatim**  
Projeto DSP II — Filtros Digitais Rejeita-Faixa  
Repositório: https://github.com/tatimmtt/DSP_II_Filtros
