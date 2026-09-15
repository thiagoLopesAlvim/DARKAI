"""
Script de testes automatizados para validação da Fase 1 da pipeline DarkAI.
Testa:
1. Geração e validação do Roteiro (Gemini / Schema)
2. Geração do Áudio da Narração (ElevenLabs / Contingência)
3. Sincronização e extração de Timestamps (Whisper / Proporcional)
4. Montagem e Renderização do Vídeo (MoviePy + Pillow sem ImageMagick)
"""

import os
import sys
import json

from gerador_roteiro import gerar_roteiro, RoteiroVideo
from gerador_audio import gerar_audio, extrair_texto_narracao
from sincronizador import sincronizar_audio, obter_duracao_audio
from editor_video import renderizar_video_moviepy, criar_frame_legenda
from main import DarkVideoPipeline


def test_01_gerador_roteiro():
    print("\n--- Teste 1: Gerador de Roteiro ---")
    tema = "O Experimento Russo do Sono"
    roteiro = gerar_roteiro(tema, salvar=True)

    assert roteiro is not None, "Roteiro não deve ser nulo"
    assert "titulo" in roteiro, "Roteiro deve conter 'titulo'"
    assert "cenas" in roteiro, "Roteiro deve conter 'cenas'"
    assert len(roteiro["cenas"]) >= 2, "Deve haver ao menos 2 cenas"

    primeira_cena = roteiro["cenas"][0]
    assert "visual_prompt" in primeira_cena, "Cena deve conter 'visual_prompt'"
    assert "narracao" in primeira_cena, "Cena deve conter 'narracao'"
    print(f"Sucesso! Roteiro gerado com {len(roteiro['cenas'])} cenas. Título: {roteiro['titulo']}")
    return roteiro


def test_02_gerador_audio(roteiro):
    print("\n--- Teste 2: Gerador de Áudio ---")
    texto = extrair_texto_narracao(roteiro)
    assert len(texto) > 10, "Texto de narração extraído deve ter conteúdo"

    caminho_audio = gerar_audio(roteiro, nome_base="teste_audio_dark")
    assert os.path.exists(caminho_audio), f"Arquivo de áudio deve existir: {caminho_audio}"
    assert os.path.getsize(caminho_audio) > 1000, "Arquivo de áudio não deve estar vazio"

    duracao = obter_duracao_audio(caminho_audio)
    assert duracao > 0.5, "Duração do áudio deve ser maior que 0.5s"
    print(f"Sucesso! Áudio gerado em {caminho_audio} com duração de {duracao:.2f}s")
    return caminho_audio


def test_03_sincronizador(caminho_audio, roteiro):
    print("\n--- Teste 3: Sincronizador de Timestamps ---")
    sync_dados = sincronizar_audio(caminho_audio, roteiro, forcar_fallback=True)

    assert sync_dados is not None, "Dados de sincronização não devem ser nulos"
    assert "cenas_timestamps" in sync_dados, "Deve conter 'cenas_timestamps'"
    assert "legendas_timestamps" in sync_dados, "Deve conter 'legendas_timestamps'"
    assert len(sync_dados["cenas_timestamps"]) == len(roteiro["cenas"]), "Qtd de timestamps de cena deve bater com roteiro"
    assert len(sync_dados["legendas_timestamps"]) > 0, "Deve conter blocos de legenda"
    print(f"Sucesso! Sincronização gerou {len(sync_dados['legendas_timestamps'])} blocos de legenda.")
    return sync_dados


def test_04_editor_video(caminho_audio, sync_dados, roteiro):
    print("\n--- Teste 4: Renderizador MoviePy (Placeholders + Legendas Pillow) ---")
    # Testa primeiro geração individual de frame de legenda RGB
    frame = criar_frame_legenda("TEXTO DE TESTE DA LEGENDA", 1920, 1080, cena_info="CENA 1")
    assert frame.shape == (1080, 1920, 3), "Frame RGB deve ter as dimensões corretas"

    # Renderiza vídeo em 16:9
    caminho_video = renderizar_video_moviepy(
        caminho_audio=caminho_audio,
        dados_sincronizacao=sync_dados,
        roteiro_dados=roteiro,
        aspect_ratio="16:9"
    )

    assert os.path.exists(caminho_video), f"Arquivo de vídeo deve existir: {caminho_video}"
    assert os.path.getsize(caminho_video) > 10000, "Vídeo MP4 gerado não deve estar vazio"
    print(f"Sucesso! Vídeo MP4 gerado com sucesso em: {caminho_video}")
    return caminho_video


def run_all_tests():
    print("==================================================")
    print("INICIANDO SUITE DE TESTES - FASE 1 DARKAI")
    print("==================================================")
    roteiro = test_01_gerador_roteiro()
    caminho_audio = test_02_gerador_audio(roteiro)
    sync_dados = test_03_sincronizador(caminho_audio, roteiro)
    caminho_video = test_04_editor_video(caminho_audio, sync_dados, roteiro)
    print("\n==================================================")
    print("TODOS OS TESTES DA FASE 1 FORAM CONCLUÍDOS COM SUCESSO!")
    print(f"Vídeo de validação gerado: {caminho_video}")
    print("==================================================")


if __name__ == "__main__":
    run_all_tests()
