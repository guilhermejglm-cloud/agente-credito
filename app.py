import streamlit as st
from groq import Groq
import PIL.Image
import pypdf
import base64
import io
from datetime import datetime
from duckduckgo_search import DDGS
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

st.set_page_config(page_title="Análise de Crédito", page_icon="🏦", layout="centered")

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
   FINANCEIRO: faturamento total e médio mensal, endividamento total, percentual de comprometimento, capacidade de pagamento real
   COMPORTAMENTO DE CRÉDITO: score, negativações (PEFIN, REFIN, protestos), histórico geral
   SÓCIOS: score individual, participações em outras empresas, risco reputacional

4. ANÁLISE DE REPUTAÇÃO E MÍDIA
   Se dados de pesquisa web forem fornecidos no contexto, analisá-los criticamente.
   Classificar como NEUTRO, ALERTA ou GRAVE.
   REGRA CRÍTICA: Se reputação = GRAVE → classificar como ALTO RISCO ou CRÍTICO automaticamente

5. IDENTIFICAÇÃO DE RED FLAGS

6. CLASSIFICAÇÃO DE RISCO: BAIXO RISCO | MÉDIO RISCO | ALTO RISCO | CRÍTICO

7. ESTRUTURAÇÃO DA OPERAÇÃO
   - LIMITE DE CRÉDITO (R$)
   - TAXA MENSAL (%)
   - PRAZO (dias)
   - NECESSIDADE DE GARANTIA (sim/não + tipo)
   - DEVEDOR SOLIDÁRIO (sim/não)

8. ESTRUTURA DO RELATÓRIO FINAL:
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

REGRAS ABSOLUTAS:
- Nunca inventar dados. Usar N/C quando necessário.
- Priorizar segurança sobre aprovação.
- Em caso de dúvida → classificar como risco maior.
- Cruzar sempre: financeiro + comportamento + reputação + percepção humana.
FILOSOFIA: "Melhor perder uma operação do que tomar um prejuízo."
"""

def img_para_base64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def chamar_modelo(api_key, mensagens):
    cliente = Groq(api_key=api_key)
    tem_imagem = any(isinstance(m.get("content"), list) for m in mensagens)
    modelo = "llama-3.2-90b-vision-preview" if tem_imagem else "llama-3.3-70b-versatile"
    resposta = cliente.chat.completions.create(model=modelo, messages=mensagens, max_tokens=8192)
    return resposta.choices[0].message.content

def ler_arquivo(uploaded_file):
    nome = uploaded_file.name
    tipo = uploaded_file.type
    dados = uploaded_file.read()
    if tipo == "application/pdf":
        try:
            reader = pypdf.PdfReader(io.BytesIO(dados))
            texto = "\n".join(p.extract_text() or "" for p in reader.pages)
            return {"tipo": "texto", "conteudo": f"[PDF: {nome}]\n{texto}"}
        except Exception as e:
            return {"tipo": "texto", "conteudo": f"[ERRO ao ler PDF '{nome}': {e}]"}
    elif tipo in ["image/jpeg", "image/jpg", "image/png"]:
        return {"tipo": "imagem", "conteudo": PIL.Image.open(io.BytesIO(dados))}
    elif tipo == "text/plain":
        return {"tipo": "texto", "conteudo": f"[DOCUMENTO: {nome}]\n{dados.decode('utf-8', errors='ignore')}"}
    return {"tipo": "texto", "conteudo": f"[Arquivo não suportado: {nome}]"}

def buscar_reputacao(nome_empresa):
    if not nome_empresa:
        return "Nome não informado — pesquisa não realizada."
    resultados = []
    try:
        with DDGS() as ddgs:
            for q in [f'"{nome_empresa}" fraude reclamação', f'"{nome_empresa}" processo judicial']:
                for h in list(ddgs.text(q, max_results=3, timelimit="y")):
                    resultados.append(f"• {h['title']}: {h['body'][:200]}")
    except Exception:
        return "Pesquisa indisponível no momento."
    return "\n".join(resultados[:6]) if resultados else f"Nenhuma ocorrência negativa encontrada para '{nome_empresa}'."

def gerar_pdf(texto_relatorio, nome_empresa="Empresa"):
    buf = io.BytesIO()
    VE = colors.HexColor("#1B4332"); VM = colors.HexColor("#2D6A4F")
    VL = colors.HexColor("#52B788"); BR = colors.white
    VR = colors.HexColor("#D62828"); TX = colors.HexColor("#0d1f12")
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    ts = ParagraphStyle("T", fontSize=16, fontName="Helvetica-Bold", textColor=BR, alignment=TA_CENTER, spaceAfter=4)
    ss = ParagraphStyle("S", fontSize=9,  fontName="Helvetica",      textColor=VL, alignment=TA_CENTER, spaceAfter=2)
    hs = ParagraphStyle("H", fontSize=10, fontName="Helvetica-Bold", textColor=BR, spaceBefore=14, spaceAfter=6, backColor=VM, leftIndent=-4, rightIndent=-4, borderPad=(4,8,4,8))
    bs = ParagraphStyle("B", fontSize=9,  fontName="Helvetica",      textColor=TX, spaceAfter=5, leading=13, alignment=TA_JUSTIFY)
    fs = ParagraphStyle("F", fontSize=9,  fontName="Helvetica-Bold", textColor=VR, spaceAfter=4)
    cs = ParagraphStyle("C", fontSize=13, fontName="Helvetica-Bold", textColor=BR, alignment=TA_CENTER, spaceBefore=8, spaceAfter=8)
    story = []
    cab = Table([[Paragraph("ANÁLISE DE CRÉDITO", ts)],[Paragraph("Antecipação de Recebíveis  |  Comitê Institucional", ss)],[Paragraph(f"Empresa: {nome_empresa}  |  Data: {datetime.now().strftime('%d/%m/%Y')}", ss)]], colWidths=[17*cm])
    cab.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),VE),("TOPPADDING",(0,0),(-1,-1),12),("BOTTOMPADDING",(0,0),(-1,-1),8),("ROUNDEDCORNERS",[8])]))
    story.append(cab); story.append(Spacer(1, 0.5*cm))
    for linha in texto_relatorio.split("\n"):
        linha = linha.strip()
        if not linha: story.append(Spacer(1, 0.15*cm)); continue
        limpo = linha.replace("**","").replace("*","").replace("`","")
        if linha.isupper() and len(linha) > 4 and not linha.startswith("-"):
            story.append(Paragraph(limpo, hs))
        elif any(k in linha.upper() for k in ["RED FLAG","⚠","ALERTA GRAVE"]):
            story.append(Paragraph(f"⚠  {limpo}", fs))
        elif any(k in linha.upper() for k in ["FAVORÁVEL","DESFAVORÁVEL"]):
            cor = VE if "FAVORÁVEL" in linha.upper() and "DES" not in linha.upper() else colors.HexColor("#6B0000")
            bl = Table([[Paragraph(limpo, cs)]], colWidths=[17*cm])
            bl.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),cor),("TOPPADDING",(0,0),(-1,-1),14),("BOTTOMPADDING",(0,0),(-1,-1),14),("ROUNDEDCORNERS",[6])]))
            story.append(bl)
        else:
            story.append(Paragraph(limpo, bs))
    doc.build(story)
    return buf.getvalue()

def tela_login():
    st.markdown('<div style="text-align:center;padding:60px 0 20px"><div style="font-size:3.5rem">🏦</div><h1 style="color:#52b788;margin:8px 0">Análise de Crédito</h1><p style="color:#74c69d;margin:0">Antecipação de Recebíveis</p></div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        senha = st.text_input("Senha", type="password", placeholder="Digite a senha de acesso")
        if st.button("Entrar", use_container_width=True):
            if senha == st.secrets.get("APP_PASSWORD", "credito2025"):
                st.session_state.autenticado = True; st.rerun()
            else:
                st.error("Senha incorreta.")

def main():
    if "autenticado" not in st.session_state: st.session_state.autenticado = False
    if not st.session_state.autenticado: tela_login(); return

    defaults = {"mensagens":[],"textos_docs":[],"imagens_docs":[],"nome_empresa":"","relatorio_pronto":False,"texto_relatorio":"","aguardando_percepcao":False}
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

    with st.sidebar:
        st.markdown("## ⚙️ API")
        api_key = st.secrets.get("GROQ_API_KEY", "")
        if not api_key:
            api_key = st.text_input("Chave Groq API", type="password", help="console.groq.com — gratuita")
        st.markdown("---"); st.markdown("## 📎 Documentos")
        arquivos = st.file_uploader("Enviar documentos", type=["pdf","png","jpg","jpeg","txt"], accept_multiple_files=True)
        nome_input = st.text_input("Razão Social / Nome", placeholder="Ex: Empresa XYZ Ltda", value=st.session_state.nome_empresa)
        if nome_input: st.session_state.nome_empresa = nome_input
        st.markdown("---")
        if st.button("🔄 Nova Análise", use_container_width=True):
            for k in defaults: st.session_state[k] = defaults[k]
            st.rerun()

    st.markdown('<div style="background:linear-gradient(135deg,#1B4332,#2D6A4F);padding:20px;border-radius:12px;margin-bottom:20px;text-align:center"><h2 style="color:white;margin:0">🏦 Análise de Crédito</h2><p style="color:#95d5b2;margin:4px 0 0">Antecipação de Recebíveis  |  Comitê Institucional</p></div>', unsafe_allow_html=True)

    for msg in st.session_state.mensagens:
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            st.markdown(msg["texto"])

    if not st.session_state.mensagens:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("▶ Iniciar Análise", use_container_width=True, type="primary"):
                if not api_key: st.error("Insira a chave da API Groq na barra lateral."); return
                textos, imagens = [], []
                if arquivos:
                    for arq in arquivos:
                        r = ler_arquivo(arq)
                        if r["tipo"] == "texto": textos.append(r["conteudo"])
                        elif r["tipo"] == "imagem": imagens.append(r["conteudo"])
                st.session_state.textos_docs = textos; st.session_state.imagens_docs = imagens
                ctx = ("\n\nDOCUMENTOS RECEBIDOS:\n" + "\n\n".join(textos) if textos else "") + (f"\n\n[{len(imagens)} imagem(ns)]" if imagens else "") or "\n\nNenhum documento enviado."
                prompt = "Recebi os documentos para análise de crédito." + ctx + "\n\nPor favor: (1) confirme o recebido, (2) sinalize problemas, (3) faça a pergunta sobre percepção do analista."
                conteudo: list = [{"type":"image_url","image_url":{"url":f"data:image/png;base64,{img_para_base64(img)}"}} for img in imagens] + [{"type":"text","text":prompt}]
                msgs = [{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":conteudo if imagens else prompt}]
                with st.spinner("Processando documentos..."):
                    try: reply = chamar_modelo(api_key, msgs)
                    except Exception as e: st.error(f"Erro ao conectar com Groq: {e}"); return
                st.session_state.mensagens.append({"role":"user","texto":"Iniciando análise."})
                st.session_state.mensagens.append({"role":"assistant","texto":reply})
                st.session_state.aguardando_percepcao = True; st.rerun()

    elif not st.session_state.relatorio_pronto:
        entrada = st.chat_input("Digite sua resposta...")
        if entrada:
            st.session_state.mensagens.append({"role":"user","texto":entrada})
            with st.chat_message("user"): st.markdown(entrada)
            if st.session_state.aguardando_percepcao:
                with st.spinner("Pesquisando reputação na web..."):
                    reputacao = buscar_reputacao(st.session_state.nome_empresa)
                prompt_final = f"PERCEPÇÃO DO ANALISTA:\n{entrada}\n\nPESQUISA DE REPUTAÇÃO:\n{reputacao}\n\nDOCUMENTOS:\n{chr(10).join(st.session_state.textos_docs) or 'Conforme processado.'}\n\nGere agora o RELATÓRIO COMPLETO até a CONCLUSÃO FINAL."
                msgs = [{"role":"system","content":SYSTEM_PROMPT}]
                for m in st.session_state.mensagens[:-1]: msgs.append({"role":"user" if m["role"]=="user" else "assistant","content":m["texto"]})
                msgs.append({"role":"user","content":prompt_final})
                with st.chat_message("assistant"):
                    with st.spinner("Gerando parecer completo..."):
                        try: relatorio = chamar_modelo(api_key, msgs)
                        except Exception as e: st.error(f"Erro: {e}"); return
                    st.markdown(relatorio)
                st.session_state.mensagens.append({"role":"assistant","texto":relatorio})
                st.session_state.texto_relatorio = relatorio; st.session_state.relatorio_pronto = True; st.session_state.aguardando_percepcao = False; st.rerun()
            else:
                msgs = [{"role":"system","content":SYSTEM_PROMPT}]
                for m in st.session_state.mensagens: msgs.append({"role":"user" if m["role"]=="user" else "assistant","content":m["texto"]})
                with st.chat_message("assistant"):
                    with st.spinner("Processando..."):
                        try: reply = chamar_modelo(api_key, msgs)
                        except Exception as e: st.error(f"Erro: {e}"); return
                    st.markdown(reply)
                st.session_state.mensagens.append({"role":"assistant","texto":reply}); st.rerun()

    if st.session_state.relatorio_pronto and st.session_state.texto_relatorio:
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            pdf = gerar_pdf(st.session_state.texto_relatorio, st.session_state.nome_empresa or "Empresa")
            nome_arq = (st.session_state.nome_empresa or "empresa").replace(" ","_").lower()
            st.download_button(label="📄 Baixar Parecer em PDF", data=pdf, file_name=f"parecer_{nome_arq}_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf", use_container_width=True, type="primary")
        st.markdown("---")
        followup = st.chat_input("Dúvidas ou ajustes no parecer?")
        if followup:
            st.session_state.relatorio_pronto = False; st.session_state.mensagens.append({"role":"user","texto":followup}); st.rerun()

if __name__ == "__main__":
    main()
