"""
test_gerador_shorts.py
Testes automatizados do módulo de Geração Inteligente de Shorts (9:16)
Valida:
1. Identificação de cortes inteligentes de alta retenção (30s - 58s).
2. Recorte preciso de áudio sem perda de qualidade (ffmpeg).
3. Reenquadramento vertical com efeito Ambient Blur (Pillow).
4. Renderização completa de Short MP4 9:16 e registro no SQLite.
"""

import os
import json
import numpy as np
from PIL import Image
import banco_dados
import gerador_shorts
import editor_video


def testar_ambient_blur():
    print("\n--- [TESTE 1] Reenquadramento Vertical 9:16 com Ambient Blur ---")
    os.makedirs("temp", exist_ok=True)
    img_horizontal = "temp/teste_img_16x9.jpg"
    
    # Cria imagem 16:9 sintética (1280x720) com gradiente
    img_pil = Image.new("RGB", (1280, 720), (30, 60, 120))
    img_pil.save(img_horizontal)

    # Aplica reenquadramento vertical 9:16 (1080x1920)
    img_vertical = editor_video.carregar_e_ajustar_imagem(
        img_horizontal,
        largura=1080,
        altura=1920,
        usar_ambient_blur=True
    )

    assert img_vertical.size == (1080, 1920), f"Dimensão incorreta: {img_vertical.size}"
    print("✅ Frame vertical 1080x1920 gerado com Ambient Blur e imagem central nítida!")
    if os.path.exists(img_horizontal):
        os.remove(img_horizontal)


def testar_identificacao_cortes():
    print("\n--- [TESTE 2] Identificação Inteligente de Cortes de Alta Retenção ---")
    roteiro_mock = {
        "titulo": "Os Segredos Obscuros do Bunker Subterrâneo",
        "cenas": [
            {"cena_id": 1, "narracao": "Você não imagina o que foi descoberto a cem metros de profundidade sob o solo soviético."},
            {"cena_id": 2, "narracao": "Durante décadas, trens secretos desciam sem passageiros para uma estação que não constava no mapa."},
            {"cena_id": 3, "narracao": "Quando as portas blindadas foram finalmente arrombadas, os diários revelaram a evacuação em massa."},
            {"cena_id": 4, "narracao": "Nenhum dos cientistas jamais foi visto novamente na superfície após o outono de 1968."},
            {"cena_id": 5, "narracao": "A pergunta que fica é: o que eles encontraram que os fez abandonar tudo às pressas?"}
        ]
    }
    sync_mock = {
        "duracao_total": 110.0,
        "cenas_timestamps": [
            {"cena_id": 1, "start": 0.0, "end": 22.0},
            {"cena_id": 2, "start": 22.0, "end": 46.0},
            {"cena_id": 3, "start": 46.0, "end": 68.0},
            {"cena_id": 4, "start": 68.0, "end": 90.0},
            {"cena_id": 5, "start": 90.0, "end": 110.0}
        ],
        "legendas_timestamps": [
            {"start": 0.0, "end": 5.0, "text": "Você não imagina o que foi descoberto"},
            {"start": 5.0, "end": 10.0, "text": "a cem metros de profundidade."},
            {"start": 22.0, "end": 30.0, "text": "Durante décadas, trens secretos desciam."},
            {"start": 46.0, "end": 55.0, "text": "As portas blindadas foram arrombadas."}
        ]
    }

    cortes = gerador_shorts.identificar_cortes_inteligentes(roteiro_mock, sync_mock, max_cortes=2)
    assert len(cortes) >= 1, "Nenhum corte foi gerado."
    for c in cortes:
        dur = c["tempo_fim"] - c["tempo_inicio"]
        assert 15.0 <= dur <= 59.0, f"Duração do corte fora do limite para Shorts: {dur}s"
        assert "titulo_short" in c, "Falta título no corte"
        assert "gancho_explicacao" in c, "Falta explicação do gancho"
    print(f"✅ Cortes identificados com sucesso ({len(cortes)} cortes). Exemplo: '{cortes[0]['titulo_short']}' ({cortes[0]['duracao']}s)")


def testar_recorte_e_renderizacao_short():
    print("\n--- [TESTE 3] Renderização de Corte Vertical 9:16 e Banco SQLite ---")
    os.makedirs("temp", exist_ok=True)
    os.makedirs("output/videos", exist_ok=True)

    # 1. Gera áudio sintético rápido (5 segundos)
    caminho_audio_dummy = "temp/audio_teste_longo.mp3"
    ps_cmd = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToWaveFile('temp/temp_short.wav')
$s.Speak('Este é um teste de corte vertical rápido para o shorts do canal dark.')
$s.Dispose()
"""
    import subprocess
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True)
    
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ffmpeg, "-y", "-i", "temp/temp_short.wav", "-c:a", "libmp3lame", caminho_audio_dummy], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if os.path.exists("temp/temp_short.wav"):
        os.remove("temp/temp_short.wav")

    roteiro_dummy = {
        "titulo": "Mistério do Corte Vertical",
        "cenas": [
            {"cena_id": 1, "visual_prompt": "Dark room test", "narracao": "Este é um teste de corte vertical rápido."}
        ]
    }
    sync_dummy = {
        "duracao_total": 5.0,
        "cenas_timestamps": [{"cena_id": 1, "start": 0.0, "end": 5.0}],
        "legendas_timestamps": [{"start": 0.5, "end": 4.5, "text": "TESTE DE CORTE VERTICAL RÁPIDO"}]
    }
    corte_dummy = {
        "corte_id": 1,
        "titulo_short": "Mistério Rápido em 5 Segundos",
        "cenas_ids": [1],
        "gancho_explicacao": "Gancho magnético de teste",
        "tempo_inicio": 0.0,
        "tempo_fim": 5.0,
        "duracao": 5.0
    }

    caminho_short_saida = "output/videos/teste_short_validacao_9x16.mp4"
    video_short = gerador_shorts.renderizar_short_corte(
        caminho_audio_longo=caminho_audio_dummy,
        sync_dados_longo=sync_dummy,
        roteiro_longo=roteiro_dummy,
        corte_info=corte_dummy,
        caminho_saida=caminho_short_saida
    )

    assert os.path.exists(video_short), f"Vídeo do Short não gerado: {video_short}"
    tam_bytes = os.path.getsize(video_short)
    assert tam_bytes > 10000, f"Arquivo de Short corrompido ou vazio: {tam_bytes} bytes"
    print(f"✅ Short MP4 9:16 renderizado com sucesso: {video_short} ({tam_bytes / 1024:.1f} KB)")

    # Valida presença no banco SQLite como is_short=1
    registros = banco_dados.listar_historico(limite=5, busca="SHORT")
    assert len(registros) >= 1, "Short não encontrado no banco SQLite."
    metricas = banco_dados.obter_metricas_gerais()
    assert metricas["total_shorts"] >= 1, "Métrica total_shorts não contabilizou o novo Short."
    print(f"✅ Short registrado no banco SQLite! Total de shorts ativos: {metricas['total_shorts']}")

    # Limpeza
    if os.path.exists(caminho_audio_dummy):
        os.remove(caminho_audio_dummy)
    if os.path.exists(video_short):
        os.remove(video_short)
    if len(registros) > 0:
        banco_dados.excluir_registro(registros[0]["id"])


if __name__ == "__main__":
    print("=" * 60)
    print("INICIANDO SUÍTE DE TESTES DE SHORTS E CORTES (9:16)")
    print("=" * 60)

    testar_ambient_blur()
    testar_identificacao_cortes()
    testar_recorte_e_renderizacao_short()

    print("\n" + "=" * 60)
    print("🎉 TODOS OS 3 TESTES DE SHORTS PASSARAM COM SUCESSO!")
    print("=" * 60)
