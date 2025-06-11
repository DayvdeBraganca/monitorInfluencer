import requests
import time
import json
from datetime import datetime

API_URL = "https://api.libanoeducacional.com.br/fl-crm/influencesExport"
CHECK_INTERVAL = 600  # segundos (10 minutos)
RELATORIO_WEBHOOK_URL = "https://discord.com/api/webhooks/SEU_WEBHOOK_AQUI"  # webhook do canal geral

with open("webhooks.json", "r") as f:
    WEBHOOKS = json.load(f)

HISTORICO = {
    name: {"sumLead": 0, "sumWins": 0}
    for name in WEBHOOKS
}

ULTIMO_ENVIADO = {
    name: {"sumLead": 0, "sumWins": 0}
    for name in WEBHOOKS
}

# Para controle de relatório diário
RELATORIO_ENVIADO = {
    "11:00": False,
    "17:30": False
}
RELATORIO_ULTIMO_TOTAL = {"sumLead": 0, "sumWins": 0}

def get_summary(influencer):
    year = datetime.now().year
    month = datetime.now().month
    url = f"{API_URL}/{year}/{month}/true/{influencer}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            return data["data"][0] if data["data"] else {}
        else:
            print(f"[ERRO] Resposta inesperada para {influencer}: {data}")
            return {}
    except Exception as e:
        print(f"[ERRO] Falha ao buscar dados de {influencer}: {e}")
        return {}

def send_to_discord(webhook_url, content):
    try:
        response = requests.post(webhook_url, json={"content": content})
        response.raise_for_status()
    except Exception as e:
        print(f"[ERRO] Falha ao enviar para Discord: {e}")

def process_influencer(name, webhook_url):
    resumo = get_summary(name)
    if not resumo:
        return

    atual_leads = resumo.get("sumLead", 0)
    atual_matriculas = resumo.get("sumWins", 0)

    anterior = HISTORICO.get(name, {"sumLead": 0, "sumWins": 0})
    enviado = ULTIMO_ENVIADO.get(name, {"sumLead": 0, "sumWins": 0})

    diff_leads = atual_leads - anterior["sumLead"]
    diff_matriculas = atual_matriculas - anterior["sumWins"]

    HISTORICO[name]["sumLead"] = atual_leads
    HISTORICO[name]["sumWins"] = atual_matriculas

    if atual_leads != enviado["sumLead"] or atual_matriculas != enviado["sumWins"]:
        mensagem = f"""📊 **Atualização para {name}:**
👥 Leads: {atual_leads} {'( +' + str(diff_leads) + ')' if diff_leads > 0 else ''}
🎓 Matrículas: {atual_matriculas} {'( +' + str(diff_matriculas) + ')' if diff_matriculas > 0 else ''}
"""
        print(f"[INFO] Notificando {name}")
        send_to_discord(webhook_url, mensagem)

        ULTIMO_ENVIADO[name]["sumLead"] = atual_leads
        ULTIMO_ENVIADO[name]["sumWins"] = atual_matriculas

def enviar_relatorio_geral():
    total_leads = sum(HISTORICO[name]["sumLead"] for name in WEBHOOKS)
    total_matriculas = sum(HISTORICO[name]["sumWins"] for name in WEBHOOKS)

    if (total_leads != RELATORIO_ULTIMO_TOTAL["sumLead"] or
        total_matriculas != RELATORIO_ULTIMO_TOTAL["sumWins"]):
        
        mensagem = f"""📅 **Relatório Geral do Dia ({datetime.now().strftime('%d/%m/%Y')}):**
👥 Total de Leads: {total_leads}
🎓 Total de Matrículas: {total_matriculas}
⏰ Horário: {datetime.now().strftime('%H:%M')}
"""
        print("[INFO] Enviando relatório geral...")
        send_to_discord(RELATORIO_WEBHOOK_URL, mensagem)

        RELATORIO_ULTIMO_TOTAL["sumLead"] = total_leads
        RELATORIO_ULTIMO_TOTAL["sumWins"] = total_matriculas
    else:
        print("[INFO] Nenhuma alteração para o relatório geral.")

def main():
    print("[INICIADO] Monitoramento de leads e matrículas...")
    while True:
        now = datetime.now()
        hora_atual = now.strftime("%H:%M")

        # Processa cada influenciador
        for name, webhook in WEBHOOKS.items():
            if webhook:
                process_influencer(name, webhook)

        # Relatórios gerais às 11:00 e 17:30
        for hora in RELATORIO_ENVIADO:
            if hora_atual == hora and not RELATORIO_ENVIADO[hora]:
                enviar_relatorio_geral()
                RELATORIO_ENVIADO[hora] = True

        # Reset diário dos flags às 00:00
        if hora_atual == "00:00":
            for hora in RELATORIO_ENVIADO:
                RELATORIO_ENVIADO[hora] = False
            print("[INFO] Flags de relatório diário resetadas.")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
