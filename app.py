import streamlit as st
import google.generativeai as genai
import PIL.Image
import pypdf
import io
from datetime import datetime
from duckduckgo_search import DDGS
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Análise de Crédito",
    page_icon="🏦",
    layout="centered"
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background-color: #0d1f12; }
[data-testid="stSidebar"]          { background-color: #112018; }
.stChatMessage                     { background-color: #1a3025 !important; border-radius: 10px; }
h1, h2, h3                         { color: #52b788 !important; }
.stButton>button                   { background-color: #2d6a4f; color: white; border: none; border-radius: 8px; }
.stButton>button:hover             { background-color: #40916c; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
ATUE COMO UM ANALISTA DE CRÉDITO SÊNIOR ESPECIALIZADO EM ANTECIPAÇÃO DE RECEBÍVEIS,
COM FOCO EM MITIGAÇÃO DE FRAUDE, ANÁLISE CRÍTICA E PRESERVAÇÃO DE CAPITAL.

SEU PERFIL:
- Extremamente criterioso, analítico e desconfiado
- Atua como um comitê de crédito institucional
- Foco principal: EVITAR PERDA (não aprovar a qualquer custo)
- Especialista em identificar inconsistências, riscos ocultos e fraudes
- Cruza dados financeiros, comportamentais e reputacionais

OBJETIVO:
Analisar documentos enviados, extrair dados, validar consistência, investigar reputação,
identificar riscos e gerar um parecer completo com recomendação de crédito e estrutura da operação.

---

FLUXO DE EXECUÇÃO:

1. VALIDAÇÃO DE ENTRADA
   - Ler todos os documentos enviados
   - Se algum arquivo não estiver legível: informar "DOCUMENTO NÃO LEGÍVEL" e solicitar reenvio
   - Se houver dados ausentes: listar exatamente quais informações estão faltando
   - Nunca assumir ou inventar dados — usar "N/C" quando necessário

2. COLETA DE INPUT HUMANO
   Na primeira interação após receber os documentos, SEMPRE fazer esta pergunta:
   "Qual foi sua percepção como analista sobre essa empresa?
   Considere: postura dos sócios, estrutura física, organização operacional,
   coerência das informações, comportamento durante interação, sinais subjetivos."
   AGUARDAR RESPOSTA ANTES DE GERAR O PARECER COMPLETO.

3. ANÁLISE ESTRUTURADA (somente após receber percepção do analista)

   EMPRESA: tempo de existência, coerência entre atividade e faturamento, estrutura vs porte declarado

   FINANCEIRO: faturamento total e médio mensal, endividamento total,
   percentual de comprometimento, capacidade de pagamento real

   COMPORTAMENTO DE CRÉDITO: score, negativações (PEFIN, REFIN, protestos), histórico geral

   SÓCIOS: score individual, participações em outras empresas, risco reputacional

4. ANÁLISE DE REPUTAÇÃO E MÍDIA
   Se dados de pesquisa web forem fornecidos no contexto, analisá-los criticamente.
   Classificar como:
   - NEUTRO: sem ocorrências relevantes
   - ALERTA: reclamações moderadas ou inconsistências menores
   - GRAVE: reportagens negativas, fraude, alto volume de reclamações
   REGRA CRÍTICA: Se reputação = GRAVE → classificar como ALTO RISCO ou CRÍTICO automaticamente

5. IDENTIFICAÇÃO DE RED FLAGS
   Exemplos: empresa recente com faturamento alto, alto endividamento + score baixo,
   divergência entre documentos, inconsistência de dados, comportamento suspeito

6. CLASSIFICAÇÃO DE RISCO: BAIXO RISCO | MÉDIO RISCO | ALTO RISCO | CRÍTICO

7. ESTRUTURAÇÃO DA OPERAÇÃO
   - LIMITE DE CRÉDITO (R$)
   - TAXA MENSAL (%)
   - PRAZO (dias)
   - NECESSIDADE DE GARANTIA (sim/não + tipo)
   - DEVEDOR SOLIDÁRIO (sim/não)
   Regra: quanto maior o risco → menor limite + maior taxa + mais garantias

8. ESTRUTURA DO RELATÓRIO FINAL (usar este formato exato):

   FICHA CADASTRAL PESSOA JURÍDICA
   DADOS DA EMPRESA
   LOCALIZAÇÃO
   DADOS BANCÁRIOS
   INFORMAÇÕES FINANCEIRAS
   CONSULTA CRÉDITO
   ANÁLISE DE REPUTAÇÃO E MÍDIA
   QUADRO SOCIETÁRIO
   ANÁLISE CRÍTICA
   RED FLAGS IDENTIFICADAS
   ESTRUTURA SUGERIDA DA OPERAÇÃO
   PARECER FINAL
   CONCLUSÃO: FAVORÁVEL / FAVORÁVEL COM RESSALVAS / DESFAVORÁVEL

---

REGRAS ABSOLUTAS:
- Nunca inventar dados
- Sempre sinalizar incerteza com N/C
- Priorizar segurança sobre aprovação
- Em caso de dúvida → classificar como risco maior
- Cruzar sempre: financeiro + comportamento + reputação + percepção humana

FILOSOFIA: "Melhor perder uma operação do que tomar um prejuízo."
"""

# ─────────────────────────────────────────────────────────────────────────────
# FUNÇÕES AUXILIARES
# ─────────────────────────────────────────────────────────────────────────────

def ler_arquivo(uploaded_file) -> dict:
    """Lê arquivo e retorna tipo + conteúdo."""
    nome = uploaded_file.name
    tipo = uploaded_file.type
    dados = uploaded_file.read()

    if tipo == "application/pdf":
        try:
            reader = pypdf.PdfReader(io.BytesIO(dados))
            texto = "\n".join(p.extract_text() or "" for p in reader.pages)
            return {"tipo": "texto", "conteudo": f"[DOCUMENTO PDF: {nome}]\n{texto}"}
        except Exception as e:
            return {"tipo": "texto", "conteudo": f"[ERRO ao ler PDF '{nome}': {e}]"}

    elif tipo in ["image/jpeg", "image/jpg", "image/png"]:
        img = PIL.Image.open(io.BytesIO(dados))
        return {"tipo": "imagem", "conteudo": img, "nome": nome}

    elif tipo == "text/plain":
        return {"tipo": "texto", "conteudo": f"[DOCUMENTO: {nome}]\n{dados.decode('utf-8', errors='ignore')}"}

    return {"tipo": "texto", "conteudo": f"[Arquivo não suportado: {nome}]"}


def buscar_reputacao(nome_empresa: str) -> str:
    """Busca reputação da empresa e sócios no DuckDuckGo."""
    if not nome_empresa:
        return "Nome da empresa não informado — pesquisa de reputação não realizada."

    resultados = []
    queries = [
        f'"{nome_empresa}" fraude reclamação',
        f'"{nome_empresa}" processo judicial',
        f'"{nome_empresa}" Reclame Aqui',
    ]

    try:
        with DDGS() as ddgs:
            for q in queries:
                hits = list(ddgs.text(q, max_results=3, timelimit="y"))
                for h in hits:
                    resultados.append(f"• {h['title']}: {h['body'][:200]}")
    except Exception:
        return "Pesquisa de reputação indisponível no momento."

    if not resultados:
        return f"Nenhuma ocorrência negativa encontrada publicamente para '{nome_empresa}'."
    return "\n".join(resultados[:9])


def gerar_pdf(texto_relatorio: str, nome_empresa: str = "Empresa") -> bytes:
    """Gera PDF profissional com tema verde escuro."""
    buf = io.BytesIO()

    VERDE_ESCURO  = colors.HexColor("#1B4332")
    VERDE_MEDIO   = colors.HexColor("#2D6A4F")
    VERDE_CLARO   = colors.HexColor("#52B788")
    BRANCO        = colors.white
    VERMELHO      = colors.HexColor("#D62828")
    TEXTO         = colors.HexColor("#0d1f12")

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=f"Parecer de Crédito — {nome_empresa}"
    )

    estilos = getSampleStyleSheet()

    titulo_s  = ParagraphStyle("Titulo", fontSize=16, fontName="Helvetica-Bold",
                               textColor=BRANCO, alignment=TA_CENTER, spaceAfter=4)
    sub_s     = ParagraphStyle("Sub", fontSize=9, fontName="Helvetica",
                               textColor=VERDE_CLARO, alignment=TA_CENTER, spaceAfter=2)
    secao_s   = ParagraphStyle("Secao", fontSize=10, fontName="Helvetica-Bold",
                               textColor=BRANCO, spaceBefore=14, spaceAfter=6,
                               backColor=VERDE_MEDIO, leftIndent=-4, rightIndent=-4,
                               borderPad=(4, 8, 4, 8))
    corpo_s   = ParagraphStyle("Corpo", fontSize=9, fontName="Helvetica",
                               textColor=TEXTO, spaceAfter=5, leading=13,
                               alignment=TA_JUSTIFY)
    flag_s    = ParagraphStyle("Flag", fontSize=9, fontName="Helvetica-Bold",
                               textColor=VERMELHO, spaceAfter=4)
    concl_s   = ParagraphStyle("Concl", fontSize=13, fontName="Helvetica-Bold",
                               textColor=BRANCO, alignment=TA_CENTER,
                               spaceBefore=8, spaceAfter=8)

    story = []

    # Cabeçalho
    cabecalho = Table(
        [[Paragraph("ANÁLISE DE CRÉDITO", titulo_s)],
         [Paragraph("Antecipação de Recebíveis  |  Comitê Institucional", sub_s)],
         [Paragraph(f"Empresa: {nome_empresa}  |  Data: {datetime.now().strftime('%d/%m/%Y')}", sub_s)]],
        colWidths=[17*cm]
    )
    cabecalho.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), VERDE_ESCURO),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [8]),
    ]))
    story.append(cabecalho)
    story.append(Spacer(1, 0.5*cm))

    # Corpo do relatório
    for linha in texto_relatorio.split("\n"):
        linha = linha.strip()
        if not linha:
            story.append(Spacer(1, 0.15*cm))
            continue

        limpo = linha.replace("**", "").replace("*", "").replace("`", "")

        if linha.isupper() and len(linha) > 4 and not linha.startswith("-"):
            story.append(Paragraph(limpo, secao_s))

        elif any(k in linha.upper() for k in ["RED FLAG", "⚠", "ALERTA GRAVE"]):
            story.append(Paragraph(f"⚠  {limpo}", flag_s))

        elif any(k in linha.upper() for k in ["FAVORÁVEL", "DESFAVORÁVEL"]):
            cor = VERDE_ESCURO if "FAVORÁVEL" in linha.upper() and "DES" not in linha.upper() \
                  else colors.HexColor("#6B0000")
            bloco = Table([[Paragraph(limpo, concl_s)]], colWidths=[17*cm])
            bloco.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), cor),
                ("TOPPADDING",    (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ("ROUNDEDCORNERS", [6]),
            ]))
            story.append(bloco)

        else:
            story.append(Paragraph(limpo, corpo_s))

    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# TELA DE LOGIN
# ─────────────────────────────────────────────────────────────────────────────
def tela_login():
    st.markdown("""
    <div style="text-align:center; padding:60px 0 20px">
        <div style="font-size:3.5rem">🏦</div>
        <h1 style="color:#52b788; margin:8px 0">Análise de Crédito</h1>
        <p style="color:#74c69d; margin:0">Antecipação de Recebíveis</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        senha = st.text_input("Senha", type="password", placeholder="Digite a senha de acesso")
        if st.button("Entrar", use_container_width=True):
            senha_correta = st.secrets.get("APP_PASSWORD", "credito2025")
            if senha == senha_correta:
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("Senha incorreta.")


# ─────────────────────────────────────────────────────────────────────────────
# APLICAÇÃO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
def main():
    # Autenticação
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False
    if not st.session_state.autenticado:
        tela_login()
        return

    # Inicializar estado
    defaults = {
        "mensagens":           [],
        "textos_docs":         [],
        "imagens_docs":        [],
        "nome_empresa":        "",
        "relatorio_pronto":    False,
        "texto_relatorio":     "",
        "aguardando_percepcao": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## ⚙️ API")
        api_key = st.secrets.get("GEMINI_API_KEY", "")
        if not api_key:
            api_key = st.text_input("Chave Gemini API", type="password",
                                    help="Obtenha em aistudio.google.com/apikey — é gratuita")

        st.markdown("---")
        st.markdown("## 📎 Documentos")
        arquivos = st.file_uploader(
            "Enviar documentos",
            type=["pdf", "png", "jpg", "jpeg", "txt"],
            accept_multiple_files=True,
            help="Contrato social, extrato, bureau, notas fiscais, RG, etc."
        )

        nome_input = st.text_input(
            "Razão Social / Nome",
            placeholder="Ex: Empresa XYZ Ltda",
            value=st.session_state.nome_empresa
        )
        if nome_input:
            st.session_state.nome_empresa = nome_input

        st.markdown("---")
        if st.button("🔄 Nova Análise", use_container_width=True):
            for k in defaults:
                st.session_state[k] = defaults[k]
            st.rerun()

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1B4332,#2D6A4F);
                padding:20px; border-radius:12px; margin-bottom:20px; text-align:center">
        <h2 style="color:white; margin:0">🏦 Análise de Crédito</h2>
        <p style="color:#95d5b2; margin:4px 0 0">Antecipação de Recebíveis  |  Comitê Institucional</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Histórico de mensagens ────────────────────────────────────────────────
    for msg in st.session_state.mensagens:
        role = "user" if msg["role"] == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(msg["texto"])

    # ── Botão iniciar análise ─────────────────────────────────────────────────
    if not st.session_state.mensagens:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("▶ Iniciar Análise", use_container_width=True, type="primary"):
                if not api_key:
                    st.error("Insira a chave da API Gemini na barra lateral.")
                    return

                # Processar arquivos enviados
                textos, imagens = [], []
                if arquivos:
                    for arq in arquivos:
                        resultado = ler_arquivo(arq)
                        if resultado["tipo"] == "texto":
                            textos.append(resultado["conteudo"])
                        elif resultado["tipo"] == "imagem":
                            imagens.append(resultado["conteudo"])

                st.session_state.textos_docs  = textos
                st.session_state.imagens_docs = imagens

                # Prompt inicial para o modelo
                contexto_docs = ""
                if textos:
                    contexto_docs = "\n\nDOCUMENTOS RECEBIDOS:\n" + "\n\n".join(textos)
                if imagens:
                    contexto_docs += f"\n\n[{len(imagens)} imagem(ns) enviada(s) — analise o conteúdo visual]"
                if not contexto_docs:
                    contexto_docs = "\n\nNenhum documento enviado. Informe ao analista o que é necessário."

                prompt_inicial = (
                    "Recebi os documentos para análise de crédito." + contexto_docs +
                    "\n\nPor favor: (1) confirme o que foi recebido, "
                    "(2) sinalize documentos ilegíveis ou dados faltantes, "
                    "(3) faça a pergunta obrigatória sobre a percepção do analista."
                )

                with st.spinner("Processando documentos..."):
                    try:
                        genai.configure(api_key=api_key)
                        modelo = genai.GenerativeModel(
                            model_name="gemini-2.0-flash",
                            system_instruction=SYSTEM_PROMPT
                        )
                        partes = imagens + [prompt_inicial]
                        resposta = modelo.generate_content(partes)
                        reply = resposta.text
                    except Exception as e:
                        st.error(f"Erro ao conectar com Gemini: {e}")
                        return

                st.session_state.mensagens.append({"role": "user",  "texto": "Iniciando análise."})
                st.session_state.mensagens.append({"role": "model", "texto": reply})
                st.session_state.aguardando_percepcao = True
                st.rerun()

    # ── Input de chat ─────────────────────────────────────────────────────────
    elif not st.session_state.relatorio_pronto:
        entrada = st.chat_input("Digite sua resposta...")

        if entrada:
            st.session_state.mensagens.append({"role": "user", "texto": entrada})
            with st.chat_message("user"):
                st.markdown(entrada)

            # Após percepção → gerar relatório completo
            if st.session_state.aguardando_percepcao:
                with st.spinner("Pesquisando reputação na web..."):
                    reputacao = buscar_reputacao(st.session_state.nome_empresa)

                textos_docs = "\n\n".join(st.session_state.textos_docs)

                prompt_final = f"""PERCEPÇÃO DO ANALISTA:
{entrada}

PESQUISA DE REPUTAÇÃO (DuckDuckGo):
{reputacao}

DOCUMENTOS (texto extraído):
{textos_docs if textos_docs else "Conforme processado anteriormente."}

Com base em tudo isso, gere agora o RELATÓRIO COMPLETO seguindo rigorosamente
a estrutura definida no sistema, do cabeçalho até a CONCLUSÃO FINAL."""

                with st.chat_message("assistant"):
                    with st.spinner("Gerando parecer completo..."):
                        try:
                            genai.configure(api_key=api_key)
                            modelo = genai.GenerativeModel(
                                model_name="gemini-2.0-flash",
                                system_instruction=SYSTEM_PROMPT
                            )
                            historico = [
                                {"role": m["role"], "parts": [m["texto"]]}
                                for m in st.session_state.mensagens[:-1]
                            ]
                            chat = modelo.start_chat(history=historico)
                            resposta = chat.send_message(
                                [*st.session_state.imagens_docs, prompt_final]
                            )
                            relatorio = resposta.text
                        except Exception as e:
                            st.error(f"Erro ao gerar relatório: {e}")
                            return

                    st.markdown(relatorio)

                st.session_state.mensagens.append({"role": "model", "texto": relatorio})
                st.session_state.texto_relatorio    = relatorio
                st.session_state.relatorio_pronto   = True
                st.session_state.aguardando_percepcao = False
                st.rerun()

            else:
                # Conversa livre após o relatório
                with st.chat_message("assistant"):
                    with st.spinner("Processando..."):
                        try:
                            genai.configure(api_key=api_key)
                            modelo = genai.GenerativeModel(
                                model_name="gemini-2.0-flash",
                                system_instruction=SYSTEM_PROMPT
                            )
                            historico = [
                                {"role": m["role"], "parts": [m["texto"]]}
                                for m in st.session_state.mensagens[:-1]
                            ]
                            chat = modelo.start_chat(history=historico)
                            resposta = chat.send_message(entrada)
                            reply = resposta.text
                        except Exception as e:
                            st.error(f"Erro: {e}")
                            return
                    st.markdown(reply)

                st.session_state.mensagens.append({"role": "model", "texto": reply})
                st.rerun()

    # ── Botão download PDF ────────────────────────────────────────────────────
    if st.session_state.relatorio_pronto and st.session_state.texto_relatorio:
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            pdf = gerar_pdf(
                st.session_state.texto_relatorio,
                st.session_state.nome_empresa or "Empresa"
            )
            nome_arq = (st.session_state.nome_empresa or "empresa") \
                       .replace(" ", "_").lower()
            st.download_button(
                label="📄 Baixar Parecer em PDF",
                data=pdf,
                file_name=f"parecer_{nome_arq}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )
        # Permite continuar conversando após gerar PDF
        st.markdown("---")
        followup = st.chat_input("Dúvidas ou ajustes no parecer?")
        if followup:
            st.session_state.relatorio_pronto = False
            st.session_state.mensagens.append({"role": "user", "texto": followup})
            st.rerun()


if __name__ == "__main__":
    main()
