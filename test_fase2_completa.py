"""
Script de testes automatizados para validação integral da Fase 2 da pipeline DarkAI.
Testa:
1. Geração de imagens por cena com gerador_imagens.py
2. Renderização do vídeo MoviePy integrando imagens reais + legendas
3. Validação do uploader do YouTube (metadados e simulação)
"""

import os
import sys
import json

from gerador_roteiro import gerar_roteiro
from gerador_audio import gerar_audio
from sincronizador import sincronizar_audio
from gerador_imagens import gerar_imagens_para_roteiro
from editor_video import renderizar_video_moviepy
from uploader_youtube import upload_video_youtube, sanitizar_metadados


def testar_fase2_completa():
    print("==================================================")
    print("INICIANDO SUITE DE TESTES - FASE 2 DARKAI")
    print("==================================================")

    # 1. Roteiro conciso de teste
    roteiro = {
        "titulo": "O Misterioso Farol de Flannan",
        "descricao": "Três guardas de farol desapareceram sem deixar vestígios em uma ilha isolada. #misterio #canaldark",
        "tags": ["mistério", "farol de flannan", "canal dark", "desaparecimentos"],
        "cenas": [
            {
                "cena_id": 1,
                "visual_prompt": "Cinematic shot of an old isolated lighthouse on rocky cliffs amidst dark stormy ocean waves, ominous fog",
                "narracao": "Em dezembro de 1900, em uma ilha remota da Escócia, algo inexplicável aconteceu."
            },
            {
                "cena_id": 2,
                "visual_prompt": "Interior of a dark vintage lighthouse room, an untouched meal on the table, cold moonlight streaming through window",
                "narracao": "Uma mesa posta para a refeição, cadeiras tombadas, e nenhum sinal dos três homens encarregados de manter a luz acesa."
            }
        ]
    }

    print("\n--- Teste 1: Geração de Imagens com IA ---")
    imagens = gerar_imagens_para_roteiro(roteiro, aspect_ratio="16:9")
    assert len(imagens) == 2, "Deve gerar imagens para as 2 cenas"
    for cid, path_img in imagens.items():
        assert os.path.exists(path_img), f"Arquivo de imagem da Cena {cid} deve existir"
        assert os.path.getsize(path_img) > 1000, f"Imagem da Cena {cid} não deve estar vazia"
        print(f"[OK] Cena {cid}: {path_img} ({os.path.getsize(path_img)} bytes)")

    print("\n--- Teste 2: Áudio e Sincronização ---")
    audio_path = gerar_audio(roteiro, nome_base="teste_farol_fase2")
    assert os.path.exists(audio_path), "Áudio deve existir"
    sync_dados = sincronizar_audio(audio_path, roteiro, forcar_fallback=True)
    assert len(sync_dados["legendas_timestamps"]) > 0, "Deve haver legendas sincronizadas"
    print(f"[OK] Áudio gerado ({audio_path}) e sincronizado com {len(sync_dados['legendas_timestamps'])} legendas.")

    print("\n--- Teste 3: Renderização de Vídeo com Imagens Reais ---")
    video_path = renderizar_video_moviepy(
        caminho_audio=audio_path,
        dados_sincronizacao=sync_dados,
        roteiro_dados=roteiro,
        aspect_ratio="16:9",
        imagens_cenas=imagens
    )
    assert os.path.exists(video_path), "Vídeo final com imagens deve existir"
    assert os.path.getsize(video_path) > 10000, "Vídeo não deve estar vazio"
    tam_mb = os.path.getsize(video_path) / (1024 * 1024)
    print(f"[OK] Vídeo final com imagens de IA renderizado com sucesso: {video_path} ({tam_mb:.2f} MB)")

    print("\n--- Teste 4: Módulo do YouTube (Validação e Simulação) ---")
    meta = sanitizar_metadados(roteiro["titulo"], roteiro["descricao"], roteiro["tags"])
    assert len(meta["title"]) <= 100
    assert len(meta["description"]) <= 5000

    yt_res = upload_video_youtube(
        caminho_video=video_path,
        titulo=roteiro["titulo"],
        descricao=roteiro["descricao"],
        tags=roteiro["tags"],
        privacidade="unlisted",
        caminho_thumbnail=imagens[1],
        forcar_simulacao=True
    )
    assert yt_res["sucesso"] is True, "Upload simulado deve retornar sucesso"
    assert "video_url" in yt_res, "Deve conter URL do YouTube"
    print(f"[OK] Uploader YouTube validado: {yt_res['video_url']} (Modo: {yt_res['modo']})")

    print("\n==================================================")
    print("TODOS OS TESTES DA FASE 2 FORAM APROVADOS COM SUCESSO!")
    print(f"Vídeo de validação da Fase 2: {video_path}")
    print("==================================================")


if __name__ == "__main__":
    testar_fase2_completa()
