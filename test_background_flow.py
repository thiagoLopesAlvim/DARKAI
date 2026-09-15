"""
Teste automatizado para validação rápida do fluxo de persistência de estado e background worker.
Usa um roteiro conciso de teste para validação ágil de todas as etapas e resiliência a F5.
"""

import os
import time
import gerenciador_estado as estado
import pipeline_worker as worker


def testar_fluxo_rapido_persistencia():
    print("\n--- Testando Persistência e Sincronização em Disco ---")
    estado.resetar_estado()
    
    est_inicial = estado.obter_estado()
    assert est_inicial["status"] == "idle"

    # 1. Simula escrita de estado em thread A
    estado.definir_status("running", etapa="roteiro")
    estado.atualizar_progresso(0.15, "Iniciando geração de roteiro...")
    estado.adicionar_log("Log de teste persistido")

    # 2. Simula leitura do estado após F5 em thread B
    est_f5 = estado.obter_estado()
    assert est_f5["status"] == "running"
    assert est_f5["progresso_valor"] == 0.15
    assert any("Log de teste persistido" in l for l in est_f5["logs"])
    print("[OK] Persistência em disco e recuperação de F5 validadas com sucesso.")

    # 3. Teste de Worker de Etapa Individual em Background
    print("\n--- Testando Worker em Background com Atualização Contínua ---")
    roteiro_teste = {
        "titulo": "Teste Rapido Background",
        "cenas": [
            {"cena_id": 1, "visual_prompt": "Dark mystery candle", "narracao": "Este é um teste ultra rápido da pipeline em background."}
        ]
    }
    
    # Dispara etapa de áudio
    disparou = worker.disparar_etapa_audio(roteiro_teste)
    assert disparou is True, "Worker deve iniciar a thread com sucesso"

    # Aguarda a conclusão monitorando o estado
    sucesso_audio = False
    for _ in range(40):
        est = estado.obter_estado()
        if est.get("status") == "idle" and est.get("audio_path") and os.path.exists(est["audio_path"]):
            sucesso_audio = True
            break
        time.sleep(0.5)

    assert sucesso_audio is True, "Áudio deve ser gerado pelo worker em background"
    audio_path = estado.obter_estado()["audio_path"]
    print(f"[OK] Worker de áudio finalizou e persistiu o arquivo: {audio_path}")

    # Dispara sincronização em modo rápido
    worker.disparar_etapa_sync(audio_path, roteiro_teste, whisper_model="base", modo_rapido=True)
    sucesso_sync = False
    for _ in range(40):
        est = estado.obter_estado()
        if est.get("status") == "idle" and est.get("sync_dados") and len(est["sync_dados"].get("legendas_timestamps", [])) > 0:
            sucesso_sync = True
            break
        time.sleep(0.5)

    assert sucesso_sync is True, "Sincronização deve ser concluída pelo worker"
    sync_dados = estado.obter_estado()["sync_dados"]
    print(f"[OK] Sincronização concluída e persistida ({len(sync_dados['legendas_timestamps'])} legendas).")

    # Dispara renderização de vídeo
    worker.disparar_etapa_video(audio_path, sync_dados, roteiro_teste, aspect_ratio="16:9")
    sucesso_video = False
    for _ in range(60):
        est = estado.obter_estado()
        prog = est.get("progresso_valor", 0.0)
        status = est.get("status")
        if status == "completed" and est.get("video_path") and os.path.exists(est["video_path"]):
            sucesso_video = True
            break
        time.sleep(0.5)

    assert sucesso_video is True, "Vídeo deve ser renderizado e persistido com sucesso"
    video_path = estado.obter_estado()["video_path"]
    print(f"[OK] Renderização de vídeo concluída: {video_path}")

    # Simulação final de recarregamento do navegador (F5)
    est_final = estado.obter_estado()
    assert est_final["status"] == "completed"
    assert est_final["progresso_valor"] == 1.0
    assert est_final["audio_path"] == audio_path
    assert est_final["video_path"] == video_path
    assert os.path.exists(est_final["video_path"])
    print("\n==================================================")
    print("TODOS OS TESTES DE PERSISTÊNCIA E WORKER PASSARAM!")
    print("Mesmo recarregando o navegador (F5), todos os dados são preservados.")
    print("==================================================")


if __name__ == "__main__":
    testar_fluxo_rapido_persistencia()
