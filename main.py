import requests
import time
import json
from datetime import datetime
import os

# --- CONFIGURAÇÕES ---
API_URL = "https://api.libanoeducacional.com.br/fl-crm/influencesExport"
CHECK_INTERVAL = 600  # segundos (10 minutos)
RELATORIO_WEBHOOK_URL = "https://discord.com/api/webhooks/1382384824534433883/5-w5d5b0S4Q6enlcCyG6H4RyvvhmaKi6RjOdTI6jpd5XvAGkUsQp_eoZFU0qZrHXssGm"

# Arquivo para persistir o estado entre reinicializações
ARQUIVO_ESTADO = "estado_notificacoes.json"

# Carrega os webhooks dos influencers do arquivo JSON
try:
    with open("webhooks.json", "r") as f:
        WEBHOOKS = json.load(f)
except FileNotFoundError:
    print("[ERRO FATAL] O arquivo 'webhooks.json' não foi encontrado. Crie o arquivo e tente novamente.")
    exit() # Encerra o script se o arquivo essencial não existir

# --- FUNÇÕES DE ESTADO ---
def carregar_estado():
    """Carrega o último estado notificado a partir de um arquivo JSON."""
    if os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, "r") as f:
            print("[INFO] Arquivo de estado encontrado. Carregando dados...")
            return json.load(f)
    else:
        print("[INFO] Arquivo de estado não encontrado. Criando um novo estado inicial.")
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

# --- FUNÇÕES DE API E DISCORD ---
def get_summary(influencer):
    """Busca os dados de um influencer específico na API."""
    year = datetime.now().year
    month = datetime.now().month
    url = f"{API_URL}/{year}/{month}/true/{influencer}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            return data["data"][0] if data["data"] else {}
        else:
            print(f"[AVISO] Resposta inesperada para {influencer}: {data}")
            return {}
    except requests.exceptions.RequestException as e:
        print(f"[ERRO] Falha ao buscar dados de {influencer}: {e}")
        return {}

def send_to_discord(webhook_url, content):
    """Envia uma mensagem para um webhook do Discord."""
    if not webhook_url:
        print("[AVISO] Webhook URL está vazia. Não é possível enviar a mensagem.")
        return
    try:
        response = requests.post(webhook_url, json={"content": content}, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[ERRO] Falha ao enviar para Discord: {e}")

# --- FUNÇÕES DE PROCESSAMENTO ---
def process_influencer(name, webhook_url, estado):
    """Processa os dados de um influencer, compara com o estado salvo e notifica se houver mudança."""
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

        print(f"[INFO] Notificando mudança para {name}...")
        send_to_discord(webhook_url, mensagem)

        # ATUALIZA o estado do influencer e SALVA no arquivo
        estado["influencers"][name] = {"sumLead": leads_atuais, "sumWins": wins_atuais}
        salvar_estado(estado)

def enviar_relatorio_geral(estado):
    """Envia o relatório geral consolidado, se houver mudanças desde o último envio."""
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
        print("[INFO] Enviando relatório geral com novos dados...")
        send_to_discord(RELATORIO_WEBHOOK_URL, mensagem)

        # ATUALIZA o estado do relatório geral e SALVA no arquivo
        estado["relatorio_geral"] = {"sumLead": total_leads_atuais, "sumWins": total_wins_atuais}
        salvar_estado(estado)
    else:
        print("[INFO] Nenhuma alteração para o relatório geral. Relatório não enviado.")

# --- FUNÇÃO PRINCIPAL ---
def main():
    print("[INICIADO] Monitoramento de leads e matrículas.")
    
    # Carrega o estado salvo ou cria um novo
    estado_atual = carregar_estado()
    
    # Flags de relatório diário (são resetados todos os dias)
    # Altere os horários aqui conforme sua necessidade
    relatorio_enviado_hoje = {
        "11:00": False,
        "23:43": False
    }

    while True:
        try:
            # Processa cada influenciador com base no estado carregado/atualizado
            for name, webhook in WEBHOOKS.items():
                process_influencer(name, webhook, estado_atual)

            # --- BLOCO DE AGENDAMENTO ROBUSTO ---
            now = datetime.now()

            for hora_agendada_str, foi_enviado in relatorio_enviado_hoje.items():
                # Converte a string da hora agendada (ex: "11:00") para um objeto time
                hora_agendada_obj = datetime.strptime(hora_agendada_str, "%H:%M").time()

                # Compara se a hora atual já passou da agendada E se ainda não foi enviada hoje
                if now.time() >= hora_agendada_obj and not foi_enviado:
                    print(f"[INFO] Hora atual ({now.strftime('%H:%M')}) passou da agendada ({hora_agendada_str}). Verificando para enviar relatório...")
                    enviar_relatorio_geral(estado_atual)
                    # Marca como enviado para não repetir no mesmo dia
                    relatorio_enviado_hoje[hora_agendada_str] = True
            
            # Reseta os flags do relatório diário à meia-noite
            if now.strftime("%H:%M") == "00:00" and any(relatorio_enviado_hoje.values()):
                for hora in relatorio_enviado_hoje:
                    relatorio_enviado_hoje[hora] = False
                print("[INFO] Novo dia! Flags de relatório diário foram resetadas.")

            # Aguarda para o próximo ciclo
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n[INFO] Script interrompido pelo usuário. Encerrando.")
            break
        except Exception as e:
            print(f"[ERRO FATAL NO LOOP PRINCIPAL] Ocorreu um erro inesperado: {e}")
            print("[INFO] Aguardando 60 segundos antes de tentar novamente...")
            time.sleep(60)

if __name__ == "__main__":
    main()