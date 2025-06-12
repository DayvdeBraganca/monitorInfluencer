import requests
import time
import json
from datetime import datetime
import os
import asyncio  # Biblioteca para operações assíncronas
import aiohttp  # Biblioteca para requisições HTTP assíncronas

# --- CONFIGURAÇÕES ---
API_URL = "https://api.libanoeducacional.com.br/fl-crm/influencesExport"
# Você pode manter um intervalo menor aqui, pois o script roda mais rápido
CHECK_INTERVAL = 600  # Exemplo: 3 minutos. Ajuste conforme necessário.
RELATORIO_WEBHOOK_URL = "https://discord.com/api/webhooks/1382384824534433883/5-w5d5b0S4Q6enlcCyG6H4RyvvhmaKi6RjOdTI6jpd5XvAGkUsQp_eoZFU0qZrHXssGm"

ARQUIVO_ESTADO = "estado_notificacoes.json"

try:
    with open("webhooks.json", "r") as f:
        WEBHOOKS = json.load(f)
except FileNotFoundError:
    print("[ERRO FATAL] O arquivo 'webhooks.json' não foi encontrado.")
    exit()

# --- FUNÇÕES DE ESTADO (Permanecem iguais) ---
def carregar_estado():
    if os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, "r") as f:
            return json.load(f)
    else:
        return {
            "influencers": {name: {"sumLead": 0, "sumWins": 0} for name in WEBHOOKS},
            "relatorio_geral": {"sumLead": 0, "sumWins": 0}
        }

def salvar_estado(estado):
    with open(ARQUIVO_ESTADO, "w") as f:
        json.dump(estado, f, indent=4)

# --- FUNÇÕES DE API E DISCORD (Agora Assíncronas) ---
async def get_summary_async(session, influencer):
    """Busca dados de forma assíncrona."""
    year, month = datetime.now().year, datetime.now().month
    url = f"{API_URL}/{year}/{month}/true/{influencer}"
    try:
        async with session.get(url, timeout=20) as response:
            response.raise_for_status()
            data = await response.json()
            if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                return influencer, data["data"][0] if data["data"] else {}
            return influencer, {}
    except Exception as e:
        print(f"[ERRO ASYNC] Falha ao buscar dados de {influencer}: {e}")
        return influencer, {}

async def send_to_discord_async(session, webhook_url, content):
    """Envia para o Discord de forma assíncrona."""
    if not webhook_url:
        return
    try:
        async with session.post(webhook_url, json={"content": content}, timeout=20) as response:
            response.raise_for_status()
    except Exception as e:
        print(f"[ERRO ASYNC] Falha ao enviar para Discord: {e}")


# --- FUNÇÃO PRINCIPAL (Agora Assíncrona) ---
async def main():
    print("[INICIADO] Monitoramento de leads e matrículas (Modo Otimizado).")
    estado_atual = carregar_estado()
    
    relatorio_enviado_hoje = {
        "11:00": False,
        "17:30": False # Altere os horários aqui conforme sua necessidade
    }

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Iniciando novo ciclo de verificação...")
                
                # 1. Processar todos os influencers de forma paralela
                tasks = [get_summary_async(session, name) for name in WEBHOOKS.keys()]
                resultados = await asyncio.gather(*tasks)

                discord_tasks = []
                for name, resumo_atual in resultados:
                    if not resumo_atual:
                        continue
                    
                    webhook_url = WEBHOOKS.get(name)
                    leads_atuais = resumo_atual.get("sumLead", 0)
                    wins_atuais = resumo_atual.get("sumWins", 0)
                    
                    ultimo_notificado = estado_atual["influencers"].get(name, {"sumLead": 0, "sumWins": 0})

                    if leads_atuais != ultimo_notificado["sumLead"] or wins_atuais != ultimo_notificado["sumWins"]:
                        diff_leads = leads_atuais - ultimo_notificado["sumLead"]
                        diff_wins = wins_atuais - ultimo_notificado["sumWins"]

                        mensagem = f"📊 **Atualização para {name}:**\n"
                        mensagem += f"👥 Leads: {leads_atuais} {'(+' + str(diff_leads) + ')' if diff_leads > 0 else ''}\n"
                        mensagem += f"🎓 Matrículas: {wins_atuais} {'(+' + str(diff_wins) + ')' if diff_wins > 0 else ''}"
                        
                        print(f"[INFO] Mudança detectada para {name}. Agendando notificação...")
                        discord_tasks.append(send_to_discord_async(session, webhook_url, mensagem))

                        estado_atual["influencers"][name] = {"sumLead": leads_atuais, "sumWins": wins_atuais}

                # 2. Enviar todas as notificações do Discord de uma vez e salvar o estado
                if discord_tasks:
                    await asyncio.gather(*discord_tasks)
                    salvar_estado(estado_atual) # Salva o estado apenas se houve mudanças
                    print("[INFO] Todas as notificações foram enviadas.")

                # 3. Lógica do Relatório Geral (permanece a mesma)
                now = datetime.now()
                for hora_agendada_str, foi_enviado in relatorio_enviado_hoje.items():
                    hora_agendada_obj = datetime.strptime(hora_agendada_str, "%H:%M").time()
                    if now.time() >= hora_agendada_obj and not foi_enviado:
                        print(f"[INFO] Verificando relatório agendado para as {hora_agendada_str}...")
                        # A função de relatório não precisa ser async, pois é chamada poucas vezes
                        enviar_relatorio_geral(estado_atual) 
                        relatorio_enviado_hoje[hora_agendada_str] = True
                
                if now.strftime("%H:%M") == "00:00" and any(relatorio_enviado_hoje.values()):
                    for hora in relatorio_enviado_hoje: relatorio_enviado_hoje[hora] = False
                    print("[INFO] Novo dia! Flags de relatório diário resetadas.")

                print(f"[{datetime.now().strftime('%H:%M:%S')}] Ciclo concluído. Aguardando {CHECK_INTERVAL} segundos...")
                await asyncio.sleep(CHECK_INTERVAL)

            except KeyboardInterrupt:
                print("\n[INFO] Script interrompido. Encerrando.")
                break
            except Exception as e:
                print(f"[ERRO FATAL NO LOOP] Ocorreu um erro: {e}. Tentando novamente em 60s.")
                await asyncio.sleep(60)

# Função síncrona para o relatório, pois não precisa de otimização
def enviar_relatorio_geral(estado):
    total_leads = sum(data["sumLead"] for data in estado["influencers"].values())
    total_wins = sum(data["sumWins"] for data in estado["influencers"].values())
    ultimo_relatorio = estado["relatorio_geral"]

    if total_leads != ultimo_relatorio["sumLead"] or total_wins != ultimo_relatorio["sumWins"]:
        mensagem = f"📅 **Relatório Geral do Dia ({datetime.now().strftime('%d/%m/%Y')}):**\n"
        mensagem += f"👥 Total de Leads: {total_leads}\n🎓 Total de Matrículas: {total_wins}\n"
        mensagem += f"⏰ Horário: {datetime.now().strftime('%H:%M')}"
        
        print("[INFO] Enviando relatório geral com novos dados...")
        # Usamos o 'requests' síncrono aqui por simplicidade
        send_to_discord(RELATORIO_WEBHOOK_URL, mensagem)
        estado["relatorio_geral"] = {"sumLead": total_leads, "sumWins": total_wins}
        salvar_estado(estado)
    else:
        print("[INFO] Nenhuma alteração para o relatório geral. Relatório não enviado.")

def send_to_discord(webhook_url, content): # Versão síncrona para o relatório
    if not webhook_url: return
    try:
        requests.post(webhook_url, json={"content": content}, timeout=15).raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[ERRO] Falha ao enviar para Discord (síncrono): {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] Programa finalizado.")