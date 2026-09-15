"""
Teste automatizado para validação da persistência de estado e execução em background.
"""

import os
import time
import gerenciador_estado as estado
import pipeline_worker as worker


def testar_persistencia_e_background():
    print("\n--- Testando Gerenciador de Estado ---")
    estado.resetar_estado()
    
    estado_inicial = estado.obter_estado()
    assert estado_inicial["status"] == "idle"
    assert estado_inicial["progresso_valor"] == 0.0

    # Atualiza progresso e adiciona log
    estado.definir_status("running", etapa="roteiro")
    estado.atualizar_progresso(0.25, "Roteiro sendo gerado...")
    estado.adicionar_log("Teste de log 123")

    # Simula reload de página (lendo arquivo fresco)
    estado_recarregado = estado.obter_estado()
    assert estado_recarregado["status"] == "running", "Status deve persistir como 'running'"
    assert estado_recarregado["progresso_valor"] == 0.25, "Progresso deve persistir como 0.25"
    assert any("Teste de log 123" in log for log in estado_recarregado["logs"]), "Log deve persistir"
    print("Sucesso: Estado foi gravado em disco e recuperado com precisão!")

    print("\n--- Testando Execução em Background com Worker ---")
    # Dispara a pipeline completa em modo rápido para testar a thread em background
    disparou = worker.disparar_pipeline_completa(
        tema="Teste de Persistencia e Background",
        aspect_ratio="16:9",
        whisper_model="base",
        modo_rapido=True
    )
    assert disparou is True, "Worker deve iniciar a thread com sucesso"

    print("Thread iniciada em background. Monitorando atualizações periódicas...")
    inicio = time.time()
    ultimo_prog = -1
    concluido = False

    while time.time() - inicio < 180:
        est = estado.obter_estado()
        prog = est.get("progresso_valor", 0.0)
        status = est.get("status")

        if prog != ultimo_prog:
            print(f"Progresso detectado na thread: {int(prog * 100)}% - {est.get('progresso_texto')}")
            ultimo_prog = prog

        if status == "completed":
            concluido = True
            break
        elif status == "error":
            raise RuntimeError(f"Erro no worker: {est.get('erro')}")

        time.sleep(0.5)

    assert concluido is True, "Pipeline em background deve finalizar com status 'completed'"
    
    # Simula recarregamento final da página (F5)
    est_final = estado.obter_estado()
    assert est_final["status"] == "completed"
    assert est_final["progresso_valor"] == 1.0
    assert est_final["roteiro"] is not None
    assert est_final["audio_path"] is not None and os.path.exists(est_final["audio_path"])
    assert est_final["sync_dados"] is not None
    assert est_final["video_path"] is not None and os.path.exists(est_final["video_path"])

    print(f"\nSucesso total! Vídeo persistido gerado: {est_final['video_path']}")
    print("Teste de resiliência a recarregamento de página (F5) APROVADO!")


if __name__ == "__main__":
    testar_persistencia_e_background()
