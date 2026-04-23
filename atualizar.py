#!/usr/bin/env python3
"""
Atualização automática do Dashboard de Produtividade Contrail.
Recalcula dias_disp, custo, margem, uso_pct para o mês atual.
Atualiza timestamps e faz commit/push.
"""

import json
import re
import os
import subprocess
from datetime import date, datetime, timedelta

PROD_HTML  = "/home/user/Dash_contrail/produtividade.html"
INDEX_HTML = "/home/user/Dash_contrail/index.html"
REPO_DIR   = "/home/user/Dash_contrail"
BRANCH     = "claude/automate-productivity-updates-v21Uz"

hoje  = date.today()
agora = datetime.now()
MES_ATUAL  = f"{hoje.year}-{hoje.month:02d}"
HOJE_ISO   = hoje.isoformat()
AGORA_STR  = agora.strftime("%d/%m/%Y %H:%M")


def contar_dias_nao_domingo(start: date, end: date) -> int:
    """Dias entre start e end (inclusive) que não são domingo."""
    if start > end:
        return 0
    count = 0
    d = start
    while d <= end:
        if d.weekday() != 6:  # 6 = domingo
            count += 1
        d += timedelta(days=1)
    return count


def ultimo_dia_mes(ano: int, mes: int) -> date:
    if mes == 12:
        return date(ano + 1, 1, 1) - timedelta(days=1)
    return date(ano, mes + 1, 1) - timedelta(days=1)


def atualizar_veiculo_mes_atual(veiculo: dict) -> dict:
    if MES_ATUAL not in veiculo.get("por_mes", {}):
        return veiculo
    dados = veiculo["por_mes"][MES_ATUAL]
    if dados is None:
        return veiculo

    ano, mes = int(MES_ATUAL[:4]), int(MES_ATUAL[5:])
    mes_inicio = date(ano, mes, 1)
    mes_fim    = ultimo_dia_mes(ano, mes)
    inicio_veiculo = date.fromisoformat(veiculo["inicio"])
    aluguel = veiculo["aluguel"]

    periodo_inicio  = max(inicio_veiculo, mes_inicio)
    dias_disp_hoje  = contar_dias_nao_domingo(periodo_inicio, min(hoje, mes_fim))
    # Total é sempre o mês completo (não desde a entrada do veículo)
    dias_disp_total = contar_dias_nao_domingo(mes_inicio, mes_fim)

    if dias_disp_total > 0:
        custo = round(aluguel * dias_disp_hoje / dias_disp_total, 2)
    else:
        custo = 0.0

    dados["dias_disp"] = dias_disp_hoje
    dados["custo"]     = custo
    dados["margem"]    = round(dados["fat"] - custo, 2)
    if dias_disp_hoje > 0:
        dados["uso_pct"] = round(dados["dias_util"] / dias_disp_hoje * 100, 1)
    else:
        dados["uso_pct"] = 0.0

    veiculo["por_mes"][MES_ATUAL] = dados
    return veiculo


def ler_const(html: str, nome: str) -> object:
    pattern = rf'^const {re.escape(nome)}\s*=\s*(.+?);?\s*$'
    m = re.search(pattern, html, re.MULTILINE)
    if not m:
        raise ValueError(f"Constante '{nome}' não encontrada no HTML")
    return json.loads(m.group(1))


def atualizar_resumo(resumo: dict, prod: list) -> dict:
    m = MES_ATUAL
    if m not in resumo:
        return resumo

    sum_agr = sum_dh = sum_dias_disp = sum_dias_util = 0
    sum_custo = 0.0
    disponiveis = utilizadas = 0

    for v in prod:
        d = v.get("por_mes", {}).get(m)
        if d is None:
            continue
        disponiveis += 1
        sum_agr        += d.get("viag_agr", 0)
        sum_dh         += d.get("viag_dh", 0)
        sum_dias_disp  += d.get("dias_disp", 0)
        sum_dias_util  += d.get("dias_util", 0)
        sum_custo      += d.get("custo", 0.0)
        if d.get("dias_util", 0) > 0:
            utilizadas += 1

    r = resumo[m]
    r["viagens_agr"]   = sum_agr
    r["viagens_dh"]    = sum_dh
    r["viagens_total"] = sum_agr + sum_dh
    r["disponiveis"]   = disponiveis
    r["utilizadas"]    = utilizadas
    r["dias_disp"]     = sum_dias_disp
    r["dias_util"]     = sum_dias_util
    r["pct_util"]      = round(sum_dias_util / sum_dias_disp * 100, 1) if sum_dias_disp > 0 else 0.0
    r["custo"]         = round(sum_custo, 2)
    # margem = fatura - custo + desconto (desconto é abatimento no custo recebido)
    r["margem"]        = round(r.get("fatura", 0.0) - sum_custo + r.get("desconto", 0.0), 2)

    resumo[m] = r
    return resumo


def recalcular_ytd(resumo: dict) -> dict:
    ytd = dict(nome="YTD", viagens_agr=0, viagens_dh=0, viagens_total=0,
               km=0.0, fatura=0.0, custo=0.0, desconto=0.0, economia=0.0,
               dias_disp=0, dias_util=0, margem=0.0)
    for r in resumo.values():
        for k in ("viagens_agr","viagens_dh","viagens_total","dias_disp","dias_util"):
            ytd[k] += r.get(k, 0)
        for k in ("km","fatura","custo","desconto","economia","margem"):
            ytd[k] += r.get(k, 0.0)
    ytd["pct_util"] = round(ytd["dias_util"] / ytd["dias_disp"] * 100, 1) if ytd["dias_disp"] > 0 else 0.0
    for k in ("km","fatura","custo","desconto","economia","margem"):
        ytd[k] = round(ytd[k], 2)
    return ytd


def substituir_const(html: str, nome: str, valor_json: str, padding: int = 0) -> str:
    pad = " " * padding
    pattern = rf'^(const {re.escape(nome)}\s*=\s*).+?;$'
    novo = f'const {nome}{pad}= {valor_json};'
    resultado = re.sub(pattern, novo, html, flags=re.MULTILINE)
    return resultado


def atualizar_produtividade(html: str, prod: list) -> str:
    prod_json = json.dumps(prod, ensure_ascii=False, separators=(',', ':'))
    html = substituir_const(html, "PROD", prod_json, padding=4)
    html = re.sub(
        r'Atualizado: \d{2}/\d{2}/\d{4} \d{2}:\d{2}',
        f'Atualizado: {AGORA_STR}',
        html
    )
    return html


def atualizar_index(html: str, resumo: dict, ytd: dict) -> str:
    html = substituir_const(html, "RESUMO",  json.dumps(resumo, ensure_ascii=False, separators=(',', ':')), padding=4)
    html = substituir_const(html, "YTD",     json.dumps(ytd,    ensure_ascii=False, separators=(',', ':')), padding=7)
    # hoje_iso
    html = re.sub(r"const hoje_iso\s*=\s*'[^']+';", f"const hoje_iso  = '{HOJE_ISO}';", html)
    # timestamps no HTML
    html = re.sub(
        r'Atualizado \d{2}/\d{2}/\d{4} \d{2}:\d{2}',
        f'Atualizado {AGORA_STR}',
        html
    )
    html = re.sub(
        r'contagem a partir de hoje \(\d{2}/\d{2}/\d{4} \d{2}:\d{2}\)',
        f'contagem a partir de hoje ({AGORA_STR})',
        html
    )
    return html


def git_cmd(*args, **kwargs):
    return subprocess.run(["git", "-C", REPO_DIR, *args], check=True, **kwargs)


def main():
    print(f"→ Atualização: {AGORA_STR}  |  Mês atual: {MES_ATUAL}")

    with open(PROD_HTML,  "r", encoding="utf-8") as f:
        prod_html = f.read()
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        index_html = f.read()

    # --- produtividade.html ---
    prod = ler_const(prod_html, "PROD")
    print(f"   PROD: {len(prod)} veículos carregados")
    prod = [atualizar_veiculo_mes_atual(v) for v in prod]

    prod_html_novo = atualizar_produtividade(prod_html, prod)
    with open(PROD_HTML, "w", encoding="utf-8") as f:
        f.write(prod_html_novo)
    print("   produtividade.html atualizado")

    # --- index.html ---
    resumo = ler_const(index_html, "RESUMO")
    resumo = atualizar_resumo(resumo, prod)
    ytd    = recalcular_ytd(resumo)

    index_html_novo = atualizar_index(index_html, resumo, ytd)
    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(index_html_novo)
    print("   index.html atualizado")

    # --- git ---
    label = agora.strftime("%d/%m/%Y %H:%M")

    git_cmd("add", "produtividade.html")
    git_cmd("commit", "-m", f"Produtividade {label}")
    print(f"   commit produtividade.html")

    git_cmd("add", "index.html")
    git_cmd("commit", "-m", f"Atualização automática {label}")
    print(f"   commit index.html")

    # push com retry
    for tentativa, espera in enumerate([0, 2, 4, 8, 16], start=1):
        if espera:
            import time; time.sleep(espera)
        try:
            git_cmd("push", "-u", "origin", BRANCH)
            print(f"   push concluído (tentativa {tentativa})")
            break
        except subprocess.CalledProcessError:
            if tentativa == 5:
                raise
            print(f"   push falhou, aguardando {espera}s...")

    print(f"✓ Concluído: {label}")


if __name__ == "__main__":
    main()
