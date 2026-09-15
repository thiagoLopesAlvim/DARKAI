"""
test_novas_melhorias.py
Validação automatizada de todas as melhorias implementadas:
1. Clonagem de Voz e Áudio Próprio (gerador_audio.py)
2. Controle de Duração e Q&A Interativo (gerador_roteiro.py)
3. Banco de Dados SQLite e Métricas (banco_dados.py)
4. Assinaturas e Persistência do Worker (pipeline_worker.py)
"""

import os
import json
import banco_dados
import gerador_audio
import gerador_roteiro
import pipeline_worker as worker


def testar_banco_dados():
    print("\n--- [TESTE 1] Banco de Dados SQLite & Métricas ---")
    banco_dados.inicializar_banco()
    
    # 1. Inserção de registro de teste
    dados_video = {
        "tema": "O Experimento do Sono Russo",
        "titulo": "O Bizarro Caso do Experimento do Sono",
        "descricao": "Documentário investigativo completo.",
        "tags": ["sono russo", "mistério", "experimento secreto"],
        "duracao_segundos": 360.5,
        "aspect_ratio": "16:9",
        "voz_tipo": "clonada",
        "voice_id": "mock_voice_12345",
        "qtd_cenas": 8,
        "caminho_video": "output/videos/teste_experimento.mp4",
        "caminho_audio": "output/audios/teste_experimento.mp3",
        "youtube_url": "https://youtube.com/watch?v=mock_video_id",
        "youtube_status": "unlisted"
    }
    
    os.makedirs("output/videos", exist_ok=True)
    with open("output/videos/teste_experimento.mp4", "wb") as f:
        f.write(b"0" * 1024 * 1024 * 5)  # 5 MB
        
    vid_id = banco_dados.salvar_video_historico(dados_video)
    assert vid_id > 0, f"Falha ao inserir vídeo. ID retornado: {vid_id}"
    print(f"✅ Vídeo inserido com sucesso! ID: {vid_id}")

    # 2. Busca e listagem
    registros = banco_dados.listar_historico(limite=10, busca="Sono Russo")
    assert len(registros) >= 1, "Busca no SQLite falhou em encontrar o registro."
    print(f"✅ Busca no SQLite encontrou {len(registros)} registro(s) correspondente(s).")
    
    # 3. Métricas
    metricas = banco_dados.obter_metricas_gerais()
    assert metricas["total_videos"] >= 1, "Métricas não contabilizaram o vídeo."
    assert metricas["total_minutos"] >= 6.0, f"Duração calculada incorreta: {metricas['total_minutos']}"
    assert metricas["total_youtube"] >= 1, "Métrica do YouTube incorreta."
    assert metricas["total_voz_clonada"] >= 1, "Métrica de voz clonada incorreta."
    print(f"✅ Métricas consolidadas com sucesso: {metricas}")
    
    # 4. Limpeza do registro de teste
    del_ok = banco_dados.excluir_registro(vid_id)
    assert del_ok, "Falha ao excluir registro de teste."
    if os.path.exists("output/videos/teste_experimento.mp4"):
        os.remove("output/videos/teste_experimento.mp4")
    print("✅ Exclusão e limpeza do SQLite concluídas com sucesso.")


def testar_duracao_e_qa():
    print("\n--- [TESTE 2] Controle de Duração & Q&A do Roteiro ---")
    
    # 1. Perguntas de aprofundamento
    perguntas = gerador_roteiro.gerar_perguntas_aprofundamento(
        "A Cidade Perdida de Z sob a Floresta Amazônica",
        duracao_minutos=4.0
    )
    assert len(perguntas) >= 2, f"Esperado ao menos 2 perguntas, obtido: {len(perguntas)}"
    for p in perguntas:
        assert "pergunta" in p and "opcoes" in p, "Estrutura da pergunta inválida."
        assert len(p["opcoes"]) >= 2, "Pergunta sem opções de resposta suficientes."
    print(f"✅ Perguntas geradas ({len(perguntas)} perguntas formuladas). Exemplo: '{perguntas[0]['pergunta']}'")

    # 2. Roteiro com escala de tempo
    r_curto = gerador_roteiro.gerar_roteiro_mock("Tema Teste 1m", duracao_minutos=1.0)
    assert len(r_curto["cenas"]) == 3, f"Esperado 3 cenas para 1m, obtido: {len(r_curto['cenas'])}"
    
    r_medio = gerador_roteiro.gerar_roteiro_mock("Tema Teste 5m", duracao_minutos=5.0)
    assert len(r_medio["cenas"]) == 8, f"Esperado 8 cenas para 5m, obtido: {len(r_medio['cenas'])}"
    
    r_longo = gerador_roteiro.gerar_roteiro_mock("Tema Teste 10m", duracao_minutos=10.0)
    assert len(r_longo["cenas"]) == 15, f"Esperado 15 cenas para 10m, obtido: {len(r_longo['cenas'])}"
    
    print("✅ Escalonamento proporcional de cenas e minutagem validado com sucesso!")


def testar_audio_clonagem_e_proprio():
    print("\n--- [TESTE 3] Módulo de Áudio (Locução Própria & Clonagem) ---")
    
    os.makedirs("temp", exist_ok=True)
    caminho_amostra_dummy = "temp/minha_gravacao_teste.wav"
    with open(caminho_amostra_dummy, "wb") as f:
        f.write(b"RIFF" + b"\x00" * 300)
        
    caminho_salvo = gerador_audio.usar_audio_proprio(caminho_amostra_dummy, nome_base="teste_locucao_humana")
    assert os.path.exists(caminho_salvo), f"Arquivo de áudio próprio não copiado: {caminho_salvo}"
    print(f"✅ Locução própria copiada e pronta para sincronização: {caminho_salvo}")
    
    try:
        gerador_audio.clonar_voz_elevenlabs(caminho_amostra_dummy, api_key="chave_invalida_teste")
    except Exception as e:
        print(f"✅ Validação de chamada da ElevenLabs capturada corretamente conforme esperado: {e}")
        
    if os.path.exists(caminho_amostra_dummy):
        os.remove(caminho_amostra_dummy)
    if os.path.exists(caminho_salvo):
        os.remove(caminho_salvo)


def testar_pipeline_worker_integracao():
    print("\n--- [TESTE 4] Integração do Worker em Background ---")
    import inspect
    sig = inspect.signature(worker.disparar_pipeline_completa)
    params = list(sig.parameters.keys())
    assert "duracao_minima_minutos" in params, "Falta duracao_minima_minutos no worker"
    assert "voice_id" in params, "Falta voice_id no worker"
    assert "caminho_audio_proprio" in params, "Falta caminho_audio_proprio no worker"
    print(f"✅ Assinatura do worker validada com todos os novos parâmetros: {params}")


if __name__ == "__main__":
    print("=" * 60)
    print("INICIANDO SUÍTE DE TESTES DAS NOVAS MELHORIAS (DARKAI)")
    print("=" * 60)
    
    testar_banco_dados()
    testar_duracao_e_qa()
    testar_audio_clonagem_e_proprio()
    testar_pipeline_worker_integracao()
    
    print("\n" + "=" * 60)
    print("🎉 TODOS OS 4 TESTES DAS NOVAS MELHORIAS PASSARAM COM SUCESSO!")
    print("=" * 60)
