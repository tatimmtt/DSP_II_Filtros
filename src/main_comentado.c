/*
 * =============================================================================
 *  main.c — Projeto Filtro Rejeita-Faixa FIR
 *  Disciplina : DSP II
 *  Plataforma : STM32F4 Discovery + Wolfson Pi Audio (codec WM5102)
 *  Objetivo   : Filtrar em tempo real o áudio que entra no LINE-IN,
 *               aplicando um FIR rejeita-faixa projetado em pyfda/Python
 *               (bandstop 400-1350 Hz, centrado em ~875 Hz, N=199, Hamming)
 *
 *  Fluxo de sinal:
 *
 *     ┌─────────┐  LINE-IN  ┌─────────┐     ┌──────────┐     ┌──────────┐
 *     │   PC    │─────────▶│  Codec  │─DMA▶│ RxBuffer │     │ TxBuffer │──┐
 *     │  (.wav) │          │ Wolfson │     │ (stereo) │     │ (stereo) │  │
 *     └─────────┘          └─────────┘     └──────────┘     └──────────┘  │
 *                                                │                ▲       │
 *                                                │                │       │
 *                                          [L]  ▼  [R]       [L]  │  [R]  │
 *                                           ┌────────┐       ┌────────┐   │
 *                                           │  FIR   │──────▶│  copy  │   │
 *                                           │(CMSIS) │       │as-is(R)│   │
 *                                           └────────┘       └────────┘   │
 *                                                                         │
 *                      DMA ─◀─────── LINE-OUT / Fone ◀────────────────────┘
 *
 *  Canais: LEFT é filtrado, RIGHT passa sem alterações (permite comparar
 *          entrada e saída lado a lado no OcenAudio / DAW).
 * =============================================================================
 */

/* ----------------------------------------------------------------------------
 * 1) Includes
 * ----------------------------------------------------------------------------
 *   stm32f4xx.h                     : HAL e periféricos do microcontrolador
 *   arm_math.h                      : Biblioteca CMSIS-DSP (tipos float32_t,
 *                                     q15_t, struct arm_fir_instance_* e
 *                                     funções arm_fir_init_* / arm_fir_*)
 *   stm32f4_discovery*.h            : Board Support Package (acelerômetro,
 *                                     LEDs, botões)
 *   wolfson_pi_audio.h              : Driver do codec de áudio (DMA, I2S)
 *   diag/Trace.h                    : trace_printf() via SWO / semihosting
 *   tests.h                         : rotina TEST_Main() do framework da aula
 *   dwt.h                           : Data Watchpoint Trace (contagem de ciclos)
 *   filter.h                        : typedef FilterTypeDef (FIR_FLOAT32/FIR_Q15)
 *   coeffs_FIR.h                    : NUM_TAPS, firCoeffs32[], firCoeffsQ15[]
 *                                     e filterType (gerado pelo script Python
 *                                     a partir do coeffs_FIR.csv do pyfda)
 * --------------------------------------------------------------------------*/
#include <stm32f4xx.h>
#include <arm_math.h>
#include <stm32f4_discovery.h>
#include <stm32f4_discovery_accelerometer.h>
#include <wolfson_pi_audio.h>
#include <diag/Trace.h>
#include <tests.h>
#include <dwt.h>
#include "filter.h"
#include "coeffs_FIR.h"

/* Descomente para medir ciclos de CPU gastos em cada bloco de filtragem */
//#define CYCLE_COUNTER


/* ----------------------------------------------------------------------------
 * 2) Definição do tamanho de bloco de processamento
 * ----------------------------------------------------------------------------
 *   WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE é o tamanho TOTAL do buffer DMA
 *   (em amostras int16_t, já intercaladas L,R,L,R,...).
 *
 *   Divisão por 4:
 *     /2  → o DMA gera uma interrupção no MEIO e outra no FIM do buffer
 *            (técnica "ping-pong" ou double-buffering). Assim processamos
 *            só metade por vez enquanto a outra metade está sendo preenchida.
 *     /2  → dentro dessa metade, só FILTRAMOS o canal LEFT (metade das
 *            amostras), então nosso bloco de trabalho tem outra divisão por 2.
 *
 *   Se WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE = 512 (256 L + 256 R),
 *   então BLOCK_SIZE = 128 amostras LEFT por interrupção.
 * --------------------------------------------------------------------------*/
#define BLOCK_SIZE (WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE)/4


/* ----------------------------------------------------------------------------
 * 3) Buffers DMA (RxBuffer = ADC in, TxBuffer = DAC out)
 * ----------------------------------------------------------------------------
 *   Estes buffers são escritos/lidos diretamente pelo DMA do codec.
 *   Por isso precisam ficar estáticos e globais (endereço fixo).
 *   Formato: amostras int16_t intercaladas em stereo: L,R,L,R,L,R,...
 * --------------------------------------------------------------------------*/
int16_t TxBuffer[WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE];
int16_t RxBuffer[WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE];

/* Flag atualizada pelas ISRs do DMA para sincronizar o main loop.
 * __IO = volatile → impede o compilador de otimizar (valor muda em IRQ). */
__IO BUFFER_StateTypeDef buffer_offset = BUFFER_OFFSET_NONE;

__IO uint8_t Volume = 70;              /* Volume 0..100, enviado ao codec   */

uint32_t AcceleroTicks;                /* Usado pelo TEST_Main (acelerômetro)*/
int16_t  AcceleroAxis[3];


/* ----------------------------------------------------------------------------
 * 4) State buffers do FIR
 * ----------------------------------------------------------------------------
 *   O FIR precisa lembrar (NUM_TAPS - 1) amostras do bloco anterior para
 *   continuar a convolução sem glitches na fronteira entre blocos.
 *   Tamanho exigido pelo CMSIS-DSP: BLOCK_SIZE + NUM_TAPS - 1.
 *   Dois buffers: um para a versão float32, outro para a versão q15.
 * --------------------------------------------------------------------------*/
static float32_t firStateF32[BLOCK_SIZE + NUM_TAPS - 1];
static q15_t     firStateQ15[BLOCK_SIZE + NUM_TAPS - 1];


/* ===========================================================================
 *                                  main()
 * =========================================================================*/
int main(int argc, char* argv[])
{
    UNUSED(argc);
    UNUSED(argv);

#ifdef CYCLE_COUNTER
    uint32_t cycleCount;
#endif

    uint32_t i, k;                                /* índices dos laços       */

    /* Buffers intermediários — só com o canal LEFT (metade do buffer DMA) */
    float32_t inputF32Buffer[BLOCK_SIZE];
    float32_t outputF32Buffer[BLOCK_SIZE];
    q15_t     inputQ15Buffer[BLOCK_SIZE];
    q15_t     outputQ15Buffer[BLOCK_SIZE];

#ifdef OS_USE_SEMIHOSTING
    /* Exemplo de semihosting — leitura de coeficientes de arquivo.
     * Mantido como no projeto original (ver bloco comentado abaixo).      */
    //FILE *CoefficientsFile;
#ifdef CYCLE_COUNTER
    FILE *CycleFile;
#endif
    //float Coefficients[NUM_TAPS];
#endif

    /* ----- 4.1) Inicialização do HAL (obrigatório no início do main) -----*/
    HAL_Init();

    /* ----- 4.2) Habilita o Data Watchpoint Trace (medição de ciclos) ----*/
    DWT_Enable();


#ifdef OS_USE_SEMIHOSTING
    /* Bloco de exemplo (desabilitado): carregar coeficientes de um arquivo
     * .txt via semihosting, só útil para debug em depuração.              */
/*  CoefficientsFile = fopen("coefficients.txt", "r");
    if (!CoefficientsFile) {
        trace_printf("Error trying to open CoefficientsFile. Check the name/location.\n");
        while(1);
    }

    for(i=0; i<5; i++)
        fscanf(CoefficientsFile, "%f", &Coefficients[i]);

    for(i=0; i<5; i++)
        trace_printf("Coefficient %d: %f\n", i, Coefficients[i]);

    fclose(CoefficientsFile);
*/

#ifdef CYCLE_COUNTER
    CycleFile = fopen("cyclecounter.txt", "w");
    if (!CycleFile) {
        trace_printf("Error trying to open cycle counter file\n.");
        while(1);
    }
#endif

#endif

    /* ------------------------------------------------------------------
     * 4.3) Inicialização do codec Wolfson
     *      - INPUT_DEVICE_LINE_IN : entrada de linha estéreo
     *      - OUTPUT_DEVICE_BOTH    : sai no fone e no line-out
     *      - 80                    : volume inicial do codec (0..100)
     *      - AUDIO_FREQUENCY_48K   : taxa de amostragem 48 kHz
     *        (CRÍTICO: precisa casar com a Fs usada no projeto do filtro)
     * ------------------------------------------------------------------*/
    WOLFSON_PI_AUDIO_Init((INPUT_DEVICE_LINE_IN << 8) | OUTPUT_DEVICE_BOTH,
                          80, AUDIO_FREQUENCY_48K);

    WOLFSON_PI_AUDIO_SetInputMode(INPUT_DEVICE_LINE_IN);

    /* Inicia mutado para evitar estouro enquanto os buffers estão zerados */
    WOLFSON_PI_AUDIO_SetMute(AUDIO_MUTE_ON);

    /* Dispara o DMA em loop: lê RxBuffer, escreve TxBuffer indefinidamente */
    WOLFSON_PI_AUDIO_Play(TxBuffer, RxBuffer, WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE);

    WOLFSON_PI_AUDIO_SetVolume(Volume);

    BSP_ACCELERO_Init();                         /* sensor (não usado aqui) */
    TEST_Init();                                 /* framework de teste      */


    /* ------------------------------------------------------------------
     * 4.4) Configuração das instâncias do FIR (CMSIS-DSP)
     * ------------------------------------------------------------------*/
    arm_fir_instance_f32 S;                      /* instância float32      */
    float32_t  *inputF32, *outputF32;

    arm_fir_instance_q15 S15;                    /* instância ponto fixo   */
    q15_t      *inputQ15, *outputQ15;
    arm_status status;

    /* Ponteiros para os buffers já alocados */
    inputF32  = &inputF32Buffer[0];
    outputF32 = &outputF32Buffer[0];
    inputQ15  = &inputQ15Buffer[0];
    outputQ15 = &outputQ15Buffer[0];

    /* arm_fir_init_f32:
     *   &S             : struct da instância FIR (será preenchida)
     *   NUM_TAPS       : nº de coeficientes (definido em coeffs_FIR.h)
     *   firCoeffs32[]  : vetor de coeficientes (float32, CMSIS-DSP)
     *   firStateF32[]  : vetor de estado (mantém histórico entre blocos)
     *   BLOCK_SIZE     : tamanho de bloco que será passado em cada chamada
     */
    arm_fir_init_f32(&S, NUM_TAPS, (float32_t *)&firCoeffs32[0],
                     &firStateF32[0], BLOCK_SIZE);

    /* arm_fir_init_q15: análogo, usando coeficientes em Q1.15.
     * ATENÇÃO: o q15 exige NUM_TAPS PAR e maior que 4.
     * O script Python (fir_header) já faz o padding com zero quando
     * NUM_TAPS original é ímpar (no nosso caso, 199 → 200).        */
    status = arm_fir_init_q15(&S15, NUM_TAPS, (q15_t *)&firCoeffsQ15[0],
                              &firStateQ15[0], BLOCK_SIZE);
    if (status == ARM_MATH_ARGUMENT_ERROR) {
        trace_printf("Problem at arm_fir_init_q15. "
                     "Check if num_taps is even and greater than 4.\n");
        while(1);
    }

    trace_printf("End of filter initialization.\n filterType is %d\n", filterType);


    /* ==================================================================
     * 5) LOOP PRINCIPAL — processamento em tempo real (ping-pong DMA)
     * ==================================================================
     *   O DMA dispara:
     *     - HalfTransfer_CallBack  → buffer_offset = BUFFER_OFFSET_HALF
     *     - TransferComplete_CallBack → buffer_offset = BUFFER_OFFSET_FULL
     *   Aqui verificamos qual metade está pronta e processamos enquanto
     *   a OUTRA metade ainda está sendo lida/escrita pelo DMA.
     * ==================================================================*/
    while (1) {

        /* ==== 5.1) PRIMEIRA METADE DO BUFFER PRONTA ==================== */
        if (buffer_offset == BUFFER_OFFSET_HALF)
        {
#ifdef CYCLE_COUNTER
            DWT_Reset();
            cycleCount = DWT_GetValue();
#endif

            /* ---------- Caminho FLOAT32 (maior precisão) -------------- */
            if (filterType == FIR_FLOAT32) {

                /* Desintercala stereo: copia só o canal LEFT para o buffer
                 * de entrada do filtro, e repete o canal RIGHT direto para
                 * TxBuffer (pass-through, para comparação).               */
                for (i = 0, k = 0; i < (WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE/2); i++) {
                    if (i % 2) {
                        /* índices ímpares = LEFT → converte int16 para float */
                        inputF32Buffer[k] = (float32_t)(RxBuffer[i]);
                        k++;
                    } else {
                        /* índices pares = RIGHT → cópia direta (pass-through) */
                        TxBuffer[i] = RxBuffer[i];
                    }
                }

                /* Filtragem: convolução do bloco com os coeficientes FIR */
                arm_fir_f32(&S, inputF32, outputF32, BLOCK_SIZE);

                /* Reintercala: devolve a saída filtrada no canal LEFT    */
                for (i = 0, k = 0; i < (WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE/2); i++) {
                    if (i % 2) {
                        TxBuffer[i] = (int16_t)(outputF32Buffer[k]);  /* back to 1.15 */
                        k++;
                    }
                }
            }

            /* ---------- Caminho Q15 (mais rápido, menor precisão) ----- */
            if (filterType == FIR_Q15) {
                for (i = 0, k = 0; i < (WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE/2); i++) {
                    if (i % 2) {
                        inputQ15Buffer[k] = (q15_t)(RxBuffer[i]);     /* já é 1.15 */
                        k++;
                    } else {
                        TxBuffer[i] = RxBuffer[i];                    /* pass-through */
                    }
                }
                arm_fir_q15(&S15, inputQ15, outputQ15, BLOCK_SIZE);
                for (i = 0, k = 0; i < (WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE/2); i++) {
                    if (i % 2) {
                        TxBuffer[i] = (int16_t)(outputQ15Buffer[k]);
                        k++;
                    }
                }
            }

#if defined(OS_USE_SEMIHOSTING) && defined(CYCLE_COUNTER)
            fprintf(CycleFile, "\nHALF: %lu", (DWT_GetValue() - cycleCount));
#endif
            /* Pronto: espera a próxima interrupção                         */
            buffer_offset = BUFFER_OFFSET_NONE;
        }


        /* ==== 5.2) SEGUNDA METADE DO BUFFER PRONTA ===================== */
        if (buffer_offset == BUFFER_OFFSET_FULL)
        {
#ifdef CYCLE_COUNTER
            DWT_Reset();
            cycleCount = DWT_GetValue();
#endif
            /* Mesma lógica da metade anterior, mas percorrendo o intervalo
             * [BUFFER_SIZE/2 .. BUFFER_SIZE-1] do RxBuffer/TxBuffer.       */
            if (filterType == FIR_FLOAT32) {
                for (i = (WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE/2), k = 0;
                     i <  WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE; i++) {
                    if (i % 2) {
                        inputF32Buffer[k] = (float32_t)(RxBuffer[i]);
                        k++;
                    } else {
                        TxBuffer[i] = RxBuffer[i];                    /* pass-through */
                    }
                }
                arm_fir_f32(&S, inputF32, outputF32, BLOCK_SIZE);
                for (i = (WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE/2), k = 0;
                     i <  WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE; i++) {
                    if (i % 2) {
                        TxBuffer[i] = (int16_t)(outputF32Buffer[k]);
                        k++;
                    }
                }
            }

            if (filterType == FIR_Q15) {
                for (i = (WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE/2), k = 0;
                     i <  WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE; i++) {
                    if (i % 2) {
                        inputQ15Buffer[k] = (q15_t)(RxBuffer[i]);
                        k++;
                    } else {
                        TxBuffer[i] = RxBuffer[i];                    /* pass-through */
                    }
                }
                arm_fir_q15(&S15, inputQ15, outputQ15, BLOCK_SIZE);
                for (i = (WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE/2), k = 0;
                     i <  WOLFSON_PI_AUDIO_TXRX_BUFFER_SIZE; i++) {
                    if (i % 2) {
                        TxBuffer[i] = (int16_t)(outputQ15Buffer[k]);
                        k++;
                    }
                }
            }

#if defined(OS_USE_SEMIHOSTING) && defined(CYCLE_COUNTER)
            fprintf(CycleFile, "\nFULL: %lu", (DWT_GetValue() - cycleCount));
#endif
            buffer_offset = BUFFER_OFFSET_NONE;
        }

        /* Tarefas auxiliares do framework de teste (LEDs, botões, etc.) */
        TEST_Main();
    }

#if defined(OS_USE_SEMIHOSTING) && defined(CYCLE_COUNTER)
    fclose(CycleFile);
#endif
    return 0;
}


/* ===========================================================================
 *                 CALLBACKS DE DMA (chamadas em contexto de IRQ)
 * ===========================================================================
 *   Mantenha-as curtíssimas: apenas sinalizam qual metade do buffer está
 *   pronta para processamento. O filtro roda no main loop, NÃO aqui.
 * =========================================================================*/

/**
 * @brief  Chamado quando o DMA termina a segunda metade do buffer (full).
 */
void WOLFSON_PI_AUDIO_TransferComplete_CallBack(void)
{
    buffer_offset = BUFFER_OFFSET_FULL;
}

/**
 * @brief  Chamado quando o DMA termina a primeira metade do buffer (half).
 */
void WOLFSON_PI_AUDIO_HalfTransfer_CallBack(void)
{
    buffer_offset = BUFFER_OFFSET_HALF;
}

/**
 * @brief  Chamado em erro de FIFO do DMA — trava em loop infinito
 *         para permitir debug com o ST-Link.
 */
void WOLFSON_PI_AUDIO_OUT_Error_CallBack(void)
{
    while (1);
}
