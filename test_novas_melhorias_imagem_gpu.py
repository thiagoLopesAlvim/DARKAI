"""
Suíte de Testes Automatizados - Melhorias de Imagens com IA, Estilos, Storytelling e GPU NVENC
Valida:
1. Detecção e Renderização acelerada por GPU (NVIDIA NVENC RTX 3070).
2. Presets de Estilos Visuais (Dark Cinematic, Analog Horror, Hiper-Realista, Dark Vintage, Cyberpunk Noir) e Prompts Negativos.
3. Bíblia Visual de Personagens e Cenários para Storytelling.
4. Geração em Proporções Nativas 16:9 e 9:16.
"""

import os
import sys
from PIL import Image

import editor_video
import gerador_imagens
import gerenciador_estado as estado


def test_1_gpu_nvenc_detection_and_render():
    print("\n--- [TESTE 1] Detecção de GPU e Renderização NVENC ---")
    gpu_info = editor_video.detectar_aceleracao_gpu()
    print(f"Informações de GPU detectadas: {gpu_info}")

    assert gpu_info["disponivel"] is True, "A GPU NVIDIA com NVENC deveria estar disponível!"
    assert "nvidia" in gpu_info["tipo"].lower(), "O tipo de GPU detectado deveria ser NVIDIA!"
    assert gpu_info["encoder"] == "h264_nvenc", "O encoder selecionado deveria ser h264_nvenc!"
    print(f"✅ GPU detectada com sucesso: {gpu_info['gpu_nome']} (Encoder: {gpu_info['encoder']})")

    # Teste de renderização rápida com MoviePy acelerado por NVENC
    os.makedirs("output/videos", exist_ok=True)
    caminho_teste_video = "output/videos/teste_nvenc_darkai.mp4"
    if os.path.exists(caminho_teste_video):
        try:
            os.remove(caminho_teste_video)
        except Exception:
            pass

    import moviepy as mp
    from moviepy import ColorClip

    clip = ColorClip(size=(640, 360), color=(15, 23, 42), duration=1.5)
    clip.write_videofile(
        caminho_teste_video,
        fps=24,
        codec="h264_nvenc",
        audio=False,
        ffmpeg_params=["-preset", "p4", "-cq", "23"]
    )
    clip.close()

    assert os.path.exists(caminho_teste_video), "O vídeo renderizado com NVENC deve existir!"
    tamanho_kb = os.path.getsize(caminho_teste_video) / 1024
    print(f"✅ Vídeo MP4 acelerado por NVENC exportado com sucesso: {caminho_teste_video} ({tamanho_kb:.1f} KB)")


def test_2_estilos_visuais_e_prompts_negativos():
    print("\n--- [TESTE 2] Presets de Estilos Visuais e Prompts Negativos ---")
    estilos_esperados = ["dark_cinematic", "analog_horror", "hiper_realista", "dark_vintage", "cyberpunk_noir"]

    for est in estilos_esperados:
        assert est in gerador_imagens.ESTILOS_VISUAIS, f"Estilo '{est}' deve estar em ESTILOS_VISUAIS!"
        cfg = gerador_imagens.ESTILOS_VISUAIS[est]
        assert len(cfg["modificador_positivo"]) > 10, f"Modificador positivo de {est} deve ser substancial!"
        assert len(cfg["prompt_negativo"]) > 10, f"Prompt negativo de {est} deve conter restrições!"
        print(f"  • {cfg['emoji']} {cfg['nome']}: Positivo ({len(cfg['modificador_positivo'])} chars), Negativo ({len(cfg['prompt_negativo'])} chars)")

    # Testa refinar_prompt_com_ia para Analog Horror
    prompt_bruto = "Eerie shadow in dark corridor"
    refinado = gerador_imagens.refinar_prompt_com_ia(
        prompt_original=prompt_bruto,
        estilo_id="analog_horror",
        cena_id=1
    )
    assert "prompt_positivo" in refinado and "prompt_negativo" in refinado
    assert "analog horror" in refinado["prompt_positivo"].lower() or "vhs" in refinado["prompt_positivo"].lower()
    assert "subtitles" in refinado["prompt_negativo"].lower() or "text" in refinado["prompt_negativo"].lower()
    print("✅ Refinamento e injeção de prompts negativos para 'analog_horror' validados!")


def test_3_biblia_visual_storytelling():
    print("\n--- [TESTE 3] Bíblia Visual de Personagens e Entorno para Storytelling ---")
    roteiro_storytelling = {
        "titulo": "O Mistério da Estação Subterrânea",
        "cenas": [
            {
                "cena_id": 1,
                "narracao": "O investigador Miller caminhava pelos trilhos da estação abandonada segurando um antigo gravador.",
                "visual_prompt": "Investigador Miller caminhando pelos trilhos da estação abandonada com casaco longo escuro"
            },
            {
                "cena_id": 2,
                "narracao": "Ao encontrar a porta de aço blindada, Miller percebeu que as luzes de emergência vermelhas ainda pulsavam.",
                "visual_prompt": "Investigador Miller examinando a pesada porta blindada sob luzes vermelhas piscando"
            }
        ]
    }

    biblia = gerador_imagens.extrair_biblia_visual(roteiro_storytelling)
    assert isinstance(biblia, dict), "A Bíblia Visual deve ser um dicionário!"
    assert "personagens" in biblia, "A Bíblia deve conter a chave 'personagens'!"
    assert "entornos" in biblia, "A Bíblia deve conter a chave 'entornos'!"
    print(f"✅ Bíblia Visual extraída com {len(biblia['personagens'])} personagens e {len(biblia['entornos'])} entornos!")

    # Testa injeção da Bíblia no prompt da Cena 1
    refinado_com_biblia = gerador_imagens.refinar_prompt_com_ia(
        prompt_original="Miller examinando um diário secreto",
        estilo_id="dark_cinematic",
        biblia_visual=biblia,
        cena_id=1,
        narracao=roteiro_storytelling["cenas"][0]["narracao"]
    )
    print(f"Prompt refinado com consistência: {refinado_com_biblia['prompt_positivo'][:100]}...")
    assert len(refinado_com_biblia["prompt_positivo"]) > 40, "O prompt refinado com consistência deve ser detalhado!"
    print("✅ Injeção de consistência de personagens no prompt validada!")


def test_4_proporcoes_nativas_e_geracao():
    print("\n--- [TESTE 4] Proporções Nativas (16:9 e 9:16) e Geração ---")
    os.makedirs("output/imagens", exist_ok=True)
    caminho_16x9 = "output/imagens/teste_aspect_16x9.jpg"
    caminho_9x16 = "output/imagens/teste_aspect_9x16.jpg"

    # Testa geração 16:9
    gerador_imagens.gerar_imagem_fallback(caminho_16x9, aspect_ratio="16:9")
    with Image.open(caminho_16x9) as img:
        assert img.size == (1280, 720), f"Dimensões 16:9 incorretas: {img.size}"
    print("✅ Proporção nativa 16:9 (1280x720) validada!")

    # Testa geração 9:16
    gerador_imagens.gerar_imagem_fallback(caminho_9x16, aspect_ratio="9:16")
    with Image.open(caminho_9x16) as img:
        assert img.size == (720, 1280), f"Dimensões 9:16 incorretas: {img.size}"
    print("✅ Proporção nativa 9:16 (720x1280) validada!")


if __name__ == "__main__":
    print("=" * 60)
    print("INICIANDO SUÍTE DE TESTES: IMAGENS, STORYTELLING E GPU NVENC")
    print("=" * 60)

    try:
        test_1_gpu_nvenc_detection_and_render()
        test_2_estilos_visuais_e_prompts_negativos()
        test_3_biblia_visual_storytelling()
        test_4_proporcoes_nativas_e_geracao()

        print("\n" + "=" * 60)
        print("🎉 TODOS OS 4 TESTES DE IMAGENS E GPU PASSARAM COM SUCESSO!")
        print("=" * 60)
        sys.exit(0)
    except AssertionError as ae:
        print(f"\n❌ FALHA NO TESTE: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERRO INESPERADO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
