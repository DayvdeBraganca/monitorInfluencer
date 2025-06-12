import requests
import time
import json
from datetime import datetime
import os # Importado para verificar se o arquivo de estado existe

API_URL = "https://api.libanoeducacional.com.br/fl-crm/influencesExport"
CHECK_INTERVAL = 600  # segundos (10 minutos)
RELATORIO_WEBHOOK_URL = "https://discord.com/api/webhooks/1382384824534433883/5-w5d5b0S4Q6enlcCyG6H4RyvvhmaKi6RjOdTI6jpd5XvAGkUsQp_eoZFU0qZrHXssGm"

# Arquivo para persistir o estado entre reinicializações
ARQUIVO_ESTADO = "estado_notificacoes.json"

with open("webhooks.json", "r") as f:
    WEBHOOKS = json.load(f)

def carregar_estado():
    """Carrega o último estado notificado a partir de um arquivo JSON."""
    if os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, "r") as f:
            return json.load(f)
    else:
        # Se o arquivo não existe, cria um estado inicial zerado
        # Inclui uma estrutura para o relatório geral também
        estado_inicial = {
            "influencers": {name: {"sumLead": 0, "sumWins": 0} for name in WEBHOOKS},
            "relatorio_geral": {"sumLead": 0, "sumWins": 0}
        }
        return estado_inicial

def salvar_estado(estado):
    """Salva o estado atual em um arquivo JSON."""
    with open(ARQUIVO_ESTADO, "w") as f:
        json.dump(estado, f, indent=4)

def get_summary(influencer):
    year = datetime.now().year
    month = datetime.now().month
    url = f"{API_URL}/{year}/{month}/true/{influencer}"
    try:
        response = requests.get(url, timeout=15) # Adicionado timeout
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            return data["data"][0] if data["data"] else {}
        else:
            print(f"[ERRO] Resposta inesperada para {influencer}: {data}")
            return {}
    except requests.exceptions.RequestException as e:
        print(f"[ERRO] Falha ao buscar dados de {influencer}: {e}")
        return {}

def send_to_discord(webhook_url, content):
    try:
        response = requests.post(webhook_url, json={"content": content}, timeout=15) # Adicionado timeout
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[ERRO] Falha ao enviar para Discord: {e}")

def process_influencer(name, webhook_url, estado):
    resumo_atual = get_summary(name)
    if not resumo_atual:
        return

    leads_atuais = resumo_atual.get("sumLead", 0)
    wins_atuais = resumo_atual.get("sumWins", 0)

    # Pega o último estado notificado para este influencer
    ultimo_notificado = estado["influencers"].get(name, {"sumLead": 0, "sumWins": 0})

    if leads_atuais != ultimo_notificado["sumLead"] or wins_atuais != ultimo_notificado["sumWins"]:
        # Calcula a diferença baseado no último estado notificado
        diff_leads = leads_atuais - ultimo_notificado["sumLead"]
        diff_wins = wins_atuais - ultimo_notificado["sumWins"]

        # Formata a mensagem apenas com as diferenças positivas
        mensagem = f"📊 **Atualização para {name}:**\n"
        mensagem += f"👥 Leads: {leads_atuais} {'(+' + str(diff_leads) + ')' if diff_leads > 0 else ''}\n"
        mensagem += f"🎓 Matrículas: {wins_atuais} {'(+' + str(diff_wins) + ')' if diff_wins > 0 else ''}"

        print(f"[INFO] Notificando {name}...")
        send_to_discord(webhook_url, mensagem)

        # ATUALIZA o estado do influencer e SALVA no arquivo
        estado["influencers"][name] = {"sumLead": leads_atuais, "sumWins": wins_atuais}
        salvar_estado(estado)

def enviar_relatorio_geral(estado):
    # Calcula os totais com base nos dados mais recentes salvos no estado
    total_leads_atuais = sum(data["sumLead"] for data in estado["influencers"].values())
    total_wins_atuais = sum(data["sumWins"] for data in estado["influencers"].values())

    ultimo_relatorio = estado["relatorio_geral"]

    if (total_leads_atuais != ultimo_relatorio["sumLead"] or
        total_wins_atuais != ultimo_relatorio["sumWins"]):

        mensagem = f"""📅 **Relatório Geral do Dia ({datetime.now().strftime('%d/%m/%Y')}):**
👥 Total de Leads: {total_leads_atuais}
🎓 Total de Matrículas: {total_wins_atuais}
⏰ Horário: {datetime.now().strftime('%H:%M')}
"""
        print("[INFO] Enviando relatório geral...")
        send_to_discord(RELATORIO_WEBHOOK_URL, mensagem)

        # ATUALIZA o estado do relatório geral e SALVA no arquivo
        estado["relatorio_geral"] = {"sumLead": total_leads_atuais, "sumWins": total_wins_atuais}
        salvar_estado(estado)
    else:
        print("[INFO] Nenhuma alteração para o relatório geral.")

def main():
    print("[INICIADO] Monitoramento de leads e matrículas...")
    
    # Carrega o estado salvo ou cria um novo
    estado_atual = carregar_estado()
    
    # Flags de relatório diário (não precisam ser persistidos)
    relatorio_enviado_hoje = {
        "11:00": False,
        "23:35": False
    }

    while True:
        now = datetime.now()
        hora_atual_str = now.strftime("%H:%M")

        # Processa cada influenciador com base no estado carregado/atualizado
        for name, webhook in WEBHOOKS.items():
            if webhook:
                # Passamos o dicionário 'estado_atual' que será modificado pelas funções
                process_influencer(name, webhook, estado_atual)

        # Verifica a necessidade de enviar relatórios gerais
        for hora_relatorio in relatorio_enviado_hoje:
            if hora_atual_str == hora_relatorio and not relatorio_enviado_hoje[hora_relatorio]:
                enviar_relatorio_geral(estado_atual)
                relatorio_enviado_hoje[hora_relatorio] = True

        # Reseta os flags do relatório diário à meia-noite
        if hora_atual_str == "00:00":
            for hora in relatorio_enviado_hoje:
                relatorio_enviado_hoje[hora] = False
            print("[INFO] Flags de relatório diário resetadas para um novo dia.")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()