#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMANAQUE VIVO
==============
Um "retrato instantâneo" de um lugar do planeta, montado em tempo real a partir
de 50 APIs públicas que NÃO exigem chave de acesso.

Em vez de apenas listar respostas, o script:
  1. Resolve o lugar (geocodificação + dados do país) e descobre fuso e moeda.
  2. Dispara as outras 48 consultas em paralelo, já parametrizadas por esse
     contexto (coordenadas, país, moeda local, data local).
  3. Cruza os resultados: consenso entre cotações de fontes independentes,
     validação cruzada da Selic, comparação do clima com o mesmo dia de 1 ano
     atrás, distância da ISS até você, etc.
  4. Tolera falhas: se uma API cair, ela é registrada e o resto segue.

Requisitos:  Python 3.9+   e   pip install requests

Uso:
    python almanaque_vivo.py                    # padrão: Fortaleza
    python almanaque_vivo.py "Tokyo"
    python almanaque_vivo.py "Lisboa" --json relatorio.json
    python almanaque_vivo.py --listar           # mostra as 50 APIs
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import statistics
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import quote

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("Dependência ausente. Instale com:  pip install requests")

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

UA = "AlmanaqueVivo/1.0 (projeto educacional; python-requests)"
CONFIG = {"timeout": 15}

GRUPOS = [
    "Lugar",
    "Atmosfera e Terra",
    "Céu e espaço",
    "Dinheiro",
    "Cultura e curiosidades",
    "Infra e tecnologia",
]

DESC_WMO = {
    0: "céu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado",
    3: "nublado", 45: "nevoeiro", 48: "nevoeiro com geada",
    51: "garoa fraca", 53: "garoa moderada", 55: "garoa forte",
    56: "garoa congelante fraca", 57: "garoa congelante forte",
    61: "chuva fraca", 63: "chuva moderada", 65: "chuva forte",
    66: "chuva congelante fraca", 67: "chuva congelante forte",
    71: "neve fraca", 73: "neve moderada", 75: "neve forte", 77: "grãos de neve",
    80: "pancadas fracas", 81: "pancadas moderadas", 82: "pancadas violentas",
    85: "pancadas de neve fracas", 86: "pancadas de neve fortes",
    95: "trovoada", 96: "trovoada com granizo", 99: "trovoada com granizo forte",
}


# ───────────────────────────── utilidades ──────────────────────────────

def get(url: str, params: dict | None = None, headers: dict | None = None,
        texto: bool = False) -> Any:
    """GET com até 3 tentativas (timeout, erro de conexão, 429 e 5xx)."""
    hdrs = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    if headers:
        hdrs.update(headers)
    for tentativa in range(3):
        try:
            r = requests.get(url, params=params, headers=hdrs,
                             timeout=CONFIG["timeout"])
        except (requests.Timeout, requests.ConnectionError):
            if tentativa < 2:
                time.sleep(1.0 * (tentativa + 1))
                continue
            raise
        if r.status_code in (429, 500, 502, 503, 504) and tentativa < 2:
            time.sleep(1.5 * (tentativa + 1))
            continue
        r.raise_for_status()
        return r.text if texto else r.json()
    raise RuntimeError("falha inesperada na requisição")  # inalcançável


def br(v: Any, casas: int = 1) -> str:
    """Formata número no padrão brasileiro (1.234,56). None vira 'n/d'."""
    if v is None:
        return "n/d"
    try:
        s = f"{float(v):,.{casas}f}"
    except (TypeError, ValueError):
        return str(v)
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def corta(txt: Any, n: int = 230) -> str:
    txt = " ".join(str(txt).split())
    return txt if len(txt) <= n else txt[: n - 1].rstrip() + "…"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def classe_eaqi(v: Any) -> str:
    if v is None:
        return "sem índice"
    for limite, rotulo in ((20, "ótima"), (40, "boa"), (60, "moderada"),
                           (80, "ruim"), (100, "muito ruim")):
        if v <= limite:
            return rotulo
    return "extremamente ruim"


def hora_local(iso: str, ctx: "Ctx") -> str:
    return datetime.fromisoformat(iso).astimezone(ctx.tzinfo()).strftime("%H:%M")


# ───────────────────────────── contexto ────────────────────────────────

@dataclass
class Ctx:
    cidade: str
    nome: str = ""
    regiao: str = ""
    pais: str = ""
    cc: str = ""
    lat: float = 0.0
    lon: float = 0.0
    tz: str = "UTC"
    moeda: str = "USD"
    pop_restcountries: int | None = None
    agora: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    hoje: date = field(default_factory=lambda: datetime.now(timezone.utc).date())

    def tzinfo(self):
        if ZoneInfo is not None:
            try:
                return ZoneInfo(self.tz)
            except Exception:
                pass
        return timezone.utc

    def atualizar_tempo(self) -> None:
        self.agora = datetime.now(self.tzinfo())
        self.hoje = self.agora.date()

    @property
    def moeda_alvo(self) -> str:
        """Moeda usada nas cotações contra o dólar (EUR se o local já usa USD)."""
        return self.moeda if self.moeda != "USD" else "EUR"

    @property
    def titulo_local(self) -> str:
        return ", ".join(p for p in (self.nome, self.regiao, self.pais) if p)


# ─────────────────────── registro das sondas (APIs) ────────────────────

@dataclass
class Sonda:
    chave: str
    grupo: str
    titulo: str
    fase: int
    fn: Callable[[Ctx], tuple]


@dataclass
class Resultado:
    chave: str
    grupo: str
    titulo: str
    ok: bool
    resumo: str
    dados: dict
    ms: int


SONDAS: list[Sonda] = []


def sonda(chave: str, grupo: str, titulo: str, fase: int = 2):
    def deco(fn):
        SONDAS.append(Sonda(chave, grupo, titulo, fase, fn))
        return fn
    return deco


def executar(s: Sonda, ctx: Ctx) -> Resultado:
    t0 = time.perf_counter()
    ok, resumo, dados = False, "", {}
    try:
        resumo, dados = s.fn(ctx)
        ok = True
    except requests.Timeout:
        resumo = "tempo esgotado"
    except requests.ConnectionError:
        resumo = "falha de conexão"
    except requests.HTTPError as e:
        codigo = e.response.status_code if e.response is not None else "?"
        resumo = f"HTTP {codigo}"
    except Exception as e:  # qualquer erro de parsing/dados
        resumo = f"{type(e).__name__}: {e}"
    ms = int((time.perf_counter() - t0) * 1000)
    return Resultado(s.chave, s.grupo, s.titulo, ok, resumo, dados or {}, ms)


# ═══════════════════════════ FASE 1 · RESOLUÇÃO ════════════════════════

@sonda("geocoding", "Lugar", "Open-Meteo · Geocodificação", fase=1)
def p_geocoding(ctx: Ctx):
    d = get("https://geocoding-api.open-meteo.com/v1/search",
            {"name": ctx.cidade, "count": 1, "language": "pt", "format": "json"})
    res = d.get("results") or []
    if not res:
        raise LookupError(f"lugar não encontrado: {ctx.cidade!r}")
    r = res[0]
    ctx.nome = r.get("name") or ctx.cidade
    ctx.regiao = r.get("admin1") or ""
    ctx.pais = r.get("country") or ""
    ctx.cc = (r.get("country_code") or "").upper()
    ctx.lat = float(r["latitude"])
    ctx.lon = float(r["longitude"])
    ctx.tz = r.get("timezone") or "UTC"
    ctx.atualizar_tempo()
    return (f"{ctx.titulo_local} · {ctx.lat:.4f}, {ctx.lon:.4f} · fuso {ctx.tz}",
            {"lat": ctx.lat, "lon": ctx.lon, "cc": ctx.cc, "tz": ctx.tz})


@sonda("restcountries", "Lugar", "REST Countries · País", fase=1)
def p_restcountries(ctx: Ctx):
    if not ctx.cc:
        raise ValueError("código do país indisponível")
    d = get(f"https://restcountries.com/v3.1/alpha/{ctx.cc}",
            {"fields": "name,capital,population,currencies,languages,region"})
    if isinstance(d, list):
        d = d[0]
    moedas = d.get("currencies") or {}
    if moedas:
        ctx.moeda = next(iter(moedas))
    langs = ", ".join((d.get("languages") or {}).values())
    cap = ", ".join(d.get("capital") or []) or "n/d"
    pop = d.get("population")
    ctx.pop_restcountries = pop
    return (f"capital {cap} · {br(pop, 0)} hab. · {d.get('region', 'n/d')} · "
            f"idiomas: {langs or 'n/d'} · moeda: {ctx.moeda}",
            {"populacao": pop, "moeda": ctx.moeda})


# ═══════════════════════════ FASE 2 · LUGAR ════════════════════════════

@sonda("nominatim", "Lugar", "OpenStreetMap Nominatim · Endereço")
def p_nominatim(ctx: Ctx):
    d = get("https://nominatim.openstreetmap.org/reverse",
            {"format": "jsonv2", "lat": ctx.lat, "lon": ctx.lon,
             "zoom": 14, "accept-language": "pt-BR"})
    if "error" in d:
        return ("sem endereço para este ponto (mar, deserto ou área remota)", {})
    return (corta(d.get("display_name", "n/d")), {})


@sonda("elevation", "Lugar", "Open-Meteo · Elevação")
def p_elevation(ctx: Ctx):
    d = get("https://api.open-meteo.com/v1/elevation",
            {"latitude": ctx.lat, "longitude": ctx.lon})
    alt = d["elevation"][0]
    return (f"{br(alt, 0)} m acima do nível do mar", {"m": alt})


@sonda("timeapi", "Lugar", "TimeAPI.io · Hora local")
def p_timeapi(ctx: Ctx):
    d = get("https://timeapi.io/api/Time/current/zone", {"timeZone": ctx.tz})
    horario = str(d.get("dateTime", ""))[:19].replace("T", " ")
    horario_verao = "horário de verão ativo" if d.get("dstActive") else "sem horário de verão"
    return (f"{horario} ({d.get('dayOfWeek', 'n/d')}), {horario_verao}", {})


@sonda("worldbank", "Lugar", "World Bank · População")
def p_worldbank(ctx: Ctx):
    if not ctx.cc:
        raise ValueError("código do país indisponível")
    d = get(f"https://api.worldbank.org/v2/country/{ctx.cc}/indicator/SP.POP.TOTL",
            {"format": "json", "mrnev": 1})
    if not isinstance(d, list) or len(d) < 2 or not d[1]:
        raise LookupError("sem dados para este país")
    linha = d[1][0]
    valor = linha.get("value")
    return (f"{br(valor, 0)} hab. (referência {linha.get('date')})",
            {"populacao": valor})


@sonda("nager", "Lugar", "Nager.Date · Próximo feriado nacional")
def p_nager(ctx: Ctx):
    d = get(f"https://date.nager.at/api/v3/NextPublicHolidays/{ctx.cc}")
    if not d:
        raise LookupError("sem feriados listados")
    h = d[0]
    dia = date.fromisoformat(h["date"])
    faltam = (dia - ctx.hoje).days
    return (f"{h.get('localName')} ({h.get('name')}) em {dia:%d/%m/%Y} — "
            f"faltam {faltam} dia(s)", {"faltam": faltam})


@sonda("wiki_summary", "Lugar", "Wikipédia (pt) · Resumo do lugar")
def p_wiki_summary(ctx: Ctx):
    titulo = quote(ctx.nome.replace(" ", "_"), safe="")
    d = get(f"https://pt.wikipedia.org/api/rest_v1/page/summary/{titulo}")
    if d.get("type") == "disambiguation":
        return (f"página ambígua na Wikipédia: {corta(d.get('extract', ''), 160)}", {})
    return (corta(d.get("extract", "sem resumo")), {})


# ═══════════════════════ FASE 2 · ATMOSFERA E TERRA ════════════════════

@sonda("forecast", "Atmosfera e Terra", "Open-Meteo · Tempo agora")
def p_forecast(ctx: Ctx):
    d = get("https://api.open-meteo.com/v1/forecast", {
        "latitude": ctx.lat, "longitude": ctx.lon, "timezone": "auto",
        "forecast_days": 1,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                   "wind_speed_10m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,uv_index_max",
    })
    c, dia = d["current"], d["daily"]
    tmax, tmin = dia["temperature_2m_max"][0], dia["temperature_2m_min"][0]
    chuva = dia["precipitation_sum"][0]
    uv = dia["uv_index_max"][0]
    desc = DESC_WMO.get(c.get("weather_code"), "condição desconhecida")
    return (f"{br(c.get('temperature_2m'))}°C (sensação {br(c.get('apparent_temperature'))}°C), "
            f"{desc}; umidade {br(c.get('relative_humidity_2m'), 0)}%, "
            f"vento {br(c.get('wind_speed_10m'))} km/h. "
            f"Hoje: {br(tmin)}–{br(tmax)}°C, chuva {br(chuva)} mm, UV máx {br(uv)}",
            {"tmax": tmax, "tmin": tmin, "temp": c.get("temperature_2m")})


@sonda("air_quality", "Atmosfera e Terra", "Open-Meteo · Qualidade do ar")
def p_air(ctx: Ctx):
    d = get("https://air-quality-api.open-meteo.com/v1/air-quality", {
        "latitude": ctx.lat, "longitude": ctx.lon, "timezone": "auto",
        "current": "european_aqi,pm10,pm2_5",
    })
    c = d["current"]
    aqi = c.get("european_aqi")
    return (f"índice europeu {br(aqi, 0)} ({classe_eaqi(aqi)}) · "
            f"PM2,5 {br(c.get('pm2_5'))} µg/m³ · PM10 {br(c.get('pm10'))} µg/m³",
            {"aqi": aqi})


@sonda("marine", "Atmosfera e Terra", "Open-Meteo Marine · Ondas")
def p_marine(ctx: Ctx):
    try:
        d = get("https://marine-api.open-meteo.com/v1/marine", {
            "latitude": ctx.lat, "longitude": ctx.lon, "timezone": "auto",
            "current": "wave_height,wave_period",
        })
    except requests.HTTPError:
        return ("sem dados marinhos (local provavelmente continental)", {})
    c = d.get("current") or {}
    if c.get("wave_height") is None:
        return ("sem dados marinhos (local provavelmente continental)", {})
    return (f"ondas de {br(c['wave_height'], 2)} m, período {br(c.get('wave_period'))} s",
            {"onda_m": c["wave_height"]})


@sonda("flood", "Atmosfera e Terra", "Open-Meteo Flood · Vazão de rios")
def p_flood(ctx: Ctx):
    try:
        d = get("https://flood-api.open-meteo.com/v1/flood", {
            "latitude": ctx.lat, "longitude": ctx.lon,
            "daily": "river_discharge", "forecast_days": 3,
        })
    except requests.HTTPError:
        return ("sem modelo hidrológico para este ponto", {})
    vals = [v for v in (d.get("daily") or {}).get("river_discharge", []) if v is not None]
    if not vals:
        return ("nenhum rio modelado perto deste ponto", {})
    return (f"vazão prevista (3 dias): {br(min(vals))}–{br(max(vals))} m³/s", {})


@sonda("archive", "Atmosfera e Terra", "Open-Meteo Archive · Mesmo dia, 1 ano atrás")
def p_archive(ctx: Ctx):
    dia = ctx.hoje - timedelta(days=365)
    d = get("https://archive-api.open-meteo.com/v1/archive", {
        "latitude": ctx.lat, "longitude": ctx.lon, "timezone": "auto",
        "start_date": dia.isoformat(), "end_date": dia.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
    })
    x = d["daily"]
    tmax, tmin = x["temperature_2m_max"][0], x["temperature_2m_min"][0]
    chuva = x["precipitation_sum"][0]
    return (f"em {dia:%d/%m/%Y}: {br(tmin)}–{br(tmax)}°C, chuva {br(chuva)} mm",
            {"tmax": tmax})


@sonda("usgs", "Atmosfera e Terra", "USGS · Último terremoto M4,5+")
def p_usgs(ctx: Ctx):
    d = get("https://earthquake.usgs.gov/fdsnws/event/1/query",
            {"format": "geojson", "limit": 1, "orderby": "time", "minmagnitude": 4.5})
    f = (d.get("features") or [None])[0]
    if not f:
        raise LookupError("nenhum evento retornado")
    p = f["properties"]
    quando = datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc)
    return (f"M{br(p.get('mag'))} · {p.get('place')} · {quando:%d/%m/%Y %H:%M} UTC", {})


@sonda("eonet", "Atmosfera e Terra", "NASA EONET · Evento natural aberto")
def p_eonet(ctx: Ctx):
    d = get("https://eonet.gsfc.nasa.gov/api/v3/events", {"status": "open", "limit": 1})
    ev = (d.get("events") or [None])[0]
    if not ev:
        raise LookupError("nenhum evento aberto")
    cats = ", ".join(c.get("title", "") for c in ev.get("categories", []))
    return (f"{ev.get('title')} ({cats or 'sem categoria'})", {})


@sonda("carbon_uk", "Atmosfera e Terra", "Carbon Intensity · Rede elétrica do Reino Unido")
def p_carbon(ctx: Ctx):
    d = get("https://api.carbonintensity.org.uk/intensity")
    i = d["data"][0]["intensity"]
    return (f"previsto {i.get('forecast')} gCO₂/kWh · medido {i.get('actual')} · "
            f"nível: {i.get('index')}", {})


# ════════════════════════════ FASE 2 · CÉU E ESPAÇO ════════════════════

@sonda("sunrise", "Céu e espaço", "Sunrise-Sunset · Sol")
def p_sunrise(ctx: Ctx):
    d = get("https://api.sunrise-sunset.org/json",
            {"lat": ctx.lat, "lng": ctx.lon, "formatted": 0, "date": ctx.hoje.isoformat()})
    if d.get("status") != "OK":
        raise RuntimeError(f"status {d.get('status')}")
    r = d["results"]
    seg = int(r["day_length"])
    return (f"nascer {hora_local(r['sunrise'], ctx)} · meio-dia solar "
            f"{hora_local(r['solar_noon'], ctx)} · pôr {hora_local(r['sunset'], ctx)} · "
            f"dia com {seg // 3600}h{(seg % 3600) // 60:02d}",
            {"dia_h": seg / 3600})


@sonda("iss", "Céu e espaço", "Where The ISS At · Estação Espacial")
def p_iss(ctx: Ctx):
    d = get("https://api.wheretheiss.at/v1/satellites/25544")
    dist = haversine_km(ctx.lat, ctx.lon, float(d["latitude"]), float(d["longitude"]))
    return (f"sobre {d['latitude']:.2f}, {d['longitude']:.2f} · altitude "
            f"{br(d.get('altitude'), 0)} km · {br(d.get('velocity'), 0)} km/h · "
            f"{d.get('visibility', 'n/d')} · a {br(dist, 0)} km de {ctx.nome}",
            {"dist_km": dist})


@sonda("swpc_kp", "Céu e espaço", "NOAA SWPC · Índice Kp (clima espacial)")
def p_kp(ctx: Ctx):
    d = get("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json")
    if not d:
        raise LookupError("resposta vazia")
    ultimo = d[-1]
    if isinstance(ultimo, dict):
        kp, quando = ultimo.get("Kp"), ultimo.get("time_tag")
    else:
        idx = {nome: i for i, nome in enumerate(d[0])}
        kp, quando = ultimo[idx["Kp"]], ultimo[idx["time_tag"]]
    kp = float(kp)
    estado = ("calmo" if kp < 4 else "instável" if kp < 5
              else "tempestade geomagnética")
    return (f"Kp {br(kp, 2)} ({estado}) em {quando}", {"kp": kp})


@sonda("open_notify", "Céu e espaço", "Open Notify · Pessoas no espaço agora")
def p_astros(ctx: Ctx):
    d = get("http://api.open-notify.org/astros.json")
    if d.get("message") != "success":
        raise RuntimeError("resposta sem sucesso")
    gente = ", ".join(f"{p.get('name')} ({p.get('craft')})" for p in d.get("people", []))
    return (f"{d.get('number')} pessoa(s) em órbita: {corta(gente, 170)}", {})


@sonda("launch_library", "Céu e espaço", "Launch Library 2 · Próximo lançamento mundial")
def p_launch(ctx: Ctx):
    d = get("https://ll.thespacedevs.com/2.2.0/launch/upcoming/", {"limit": 1})
    r = (d.get("results") or [None])[0]
    if not r:
        raise LookupError("nenhum lançamento listado")
    net = datetime.fromisoformat(str(r["net"]).replace("Z", "+00:00"))
    local = net.astimezone(ctx.tzinfo()).strftime("%d/%m/%Y %H:%M")
    status = (r.get("status") or {}).get("name", "n/d")
    return (f"{r.get('name')} · {local} (horário de {ctx.nome}) · {status}", {})


# ═════════════════════════════ FASE 2 · DINHEIRO ═══════════════════════

@sonda("awesomeapi", "Dinheiro", "AwesomeAPI · Câmbio USD→moeda local")
def p_awesome(ctx: Ctx):
    alvo = ctx.moeda_alvo
    d = get(f"https://economia.awesomeapi.com.br/json/last/USD-{alvo}")
    item = d[f"USD{alvo}"]
    taxa = float(item["bid"])
    return (f"1 USD = {br(taxa, 4)} {alvo} (variação no dia {br(item.get('pctChange'), 2)}%)",
            {"taxa": taxa})


@sonda("frankfurter", "Dinheiro", "Frankfurter (BCE) · Câmbio USD→moeda local")
def p_frankfurter(ctx: Ctx):
    alvo = ctx.moeda_alvo
    d = get("https://api.frankfurter.dev/v1/latest", {"base": "USD", "symbols": alvo})
    taxa = float(d["rates"][alvo])
    return (f"1 USD = {br(taxa, 4)} {alvo} (referência {d.get('date')})", {"taxa": taxa})


@sonda("er_api", "Dinheiro", "ExchangeRate-API (aberta) · Câmbio USD→moeda local")
def p_er_api(ctx: Ctx):
    alvo = ctx.moeda_alvo
    d = get("https://open.er-api.com/v6/latest/USD")
    if d.get("result") != "success":
        raise RuntimeError("resposta sem sucesso")
    taxa = float(d["rates"][alvo])
    return (f"1 USD = {br(taxa, 4)} {alvo}", {"taxa": taxa})


@sonda("coinbase", "Dinheiro", "Coinbase · Bitcoin (USD)")
def p_coinbase(ctx: Ctx):
    d = get("https://api.coinbase.com/v2/prices/BTC-USD/spot")
    preco = float(d["data"]["amount"])
    return (f"US$ {br(preco, 2)}", {"preco": preco})


@sonda("kraken", "Dinheiro", "Kraken · Bitcoin (USD)")
def p_kraken(ctx: Ctx):
    d = get("https://api.kraken.com/0/public/Ticker", {"pair": "XBTUSD"})
    if d.get("error"):
        raise RuntimeError("; ".join(d["error"]))
    info = next(iter(d["result"].values()))
    preco = float(info["c"][0])
    return (f"US$ {br(preco, 2)}", {"preco": preco})


@sonda("coingecko", "Dinheiro", "CoinGecko · Bitcoin (USD)")
def p_coingecko(ctx: Ctx):
    d = get("https://api.coingecko.com/api/v3/simple/price",
            {"ids": "bitcoin", "vs_currencies": "usd"})
    preco = float(d["bitcoin"]["usd"])
    return (f"US$ {br(preco, 2)}", {"preco": preco})


@sonda("bcb_selic", "Dinheiro", "Banco Central do Brasil · Meta Selic")
def p_bcb(ctx: Ctx):
    d = get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1",
            {"formato": "json"})
    linha = d[0]
    valor = float(linha["valor"])
    return (f"{br(valor, 2)}% a.a. (série atualizada em {linha['data']})", {"valor": valor})


@sonda("brasilapi_taxas", "Dinheiro", "BrasilAPI · Taxas (Selic/CDI/IPCA)")
def p_brasilapi_taxas(ctx: Ctx):
    d = get("https://brasilapi.com.br/api/taxas/v1")
    m = {str(i.get("nome", "")).lower(): i.get("valor") for i in d}
    return (f"Selic {br(m.get('selic'), 2)}% · CDI {br(m.get('cdi'), 2)}% · "
            f"IPCA {br(m.get('ipca'), 2)}%", {"selic": m.get("selic")})


@sonda("ibge_noticias", "Dinheiro", "IBGE · Notícia mais recente")
def p_ibge(ctx: Ctx):
    d = get("https://servicodados.ibge.gov.br/api/v3/noticias/", {"qtd": 1})
    it = (d.get("items") or [None])[0]
    if not it:
        raise LookupError("sem notícias")
    return (f"{corta(it.get('titulo'), 150)} ({str(it.get('data_publicacao', ''))[:10]})", {})


@sonda("viacep", "Dinheiro", "ViaCEP · Marco zero de São Paulo")
def p_viacep(ctx: Ctx):
    d = get("https://viacep.com.br/ws/01001000/json/")
    if d.get("erro"):
        raise LookupError("CEP não encontrado")
    return (f"{d.get('logradouro')}, {d.get('bairro')} — {d.get('localidade')}/{d.get('uf')}", {})


# ═════════════════════ FASE 2 · CULTURA E CURIOSIDADES ═════════════════

@sonda("wiki_onthisday", "Cultura e curiosidades", "Wikimedia · Neste dia na história (en)")
def p_onthisday(ctx: Ctx):
    d = get("https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/events/"
            f"{ctx.hoje.month:02d}/{ctx.hoje.day:02d}")
    eventos = d.get("events") or []
    if not eventos:
        raise LookupError("sem eventos")
    e = random.Random(ctx.hoje.toordinal()).choice(eventos)
    return (f"{e.get('year')}: {corta(e.get('text'), 200)}", {})


@sonda("wiki_top", "Cultura e curiosidades", "Wikimedia · Artigos mais lidos (en)")
def p_wiki_top(ctx: Ctx):
    dia = ctx.hoje - timedelta(days=3)
    d = get("https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/"
            f"all-access/{dia:%Y}/{dia:%m}/{dia:%d}")
    artigos = d["items"][0]["articles"]
    top = []
    for a in artigos:
        nome = a.get("article", "")
        if nome in ("Main_Page", "-") or ":" in nome:
            continue
        top.append(f"{nome.replace('_', ' ')} ({br(a.get('views'), 0)})")
        if len(top) == 3:
            break
    if not top:
        raise LookupError("sem artigos")
    return (f"em {dia:%d/%m}: " + " · ".join(top), {})


@sonda("openlibrary", "Cultura e curiosidades", "Open Library · Livro ligado ao lugar")
def p_openlibrary(ctx: Ctx):
    d = get("https://openlibrary.org/search.json",
            {"q": ctx.nome, "limit": 1, "fields": "title,author_name,first_publish_year"})
    docs = d.get("docs") or []
    if not docs:
        return (f"nenhum livro encontrado para {ctx.nome!r}", {})
    x = docs[0]
    autor = ", ".join(x.get("author_name") or ["autor desconhecido"])
    return (f"{x.get('title')} — {autor} ({x.get('first_publish_year', 's/d')})", {})


@sonda("catfact", "Cultura e curiosidades", "Cat Fact · Fato sobre gatos")
def p_catfact(ctx: Ctx):
    d = get("https://catfact.ninja/fact")
    return (corta(d["fact"], 200), {})


@sonda("dogceo", "Cultura e curiosidades", "Dog CEO · Raça sorteada")
def p_dogceo(ctx: Ctx):
    d = get("https://dog.ceo/api/breeds/image/random")
    url = str(d["message"])
    raca = url.split("/breeds/")[1].split("/")[0].replace("-", " ")
    return (f"{raca} ({url})", {})


@sonda("poetrydb", "Cultura e curiosidades", "PoetryDB · Poema sorteado")
def p_poetrydb(ctx: Ctx):
    d = get("https://poetrydb.org/random/1")
    p = d[0]
    return (f"{p.get('title')} — {p.get('author')} ({p.get('linecount')} versos)", {})


@sonda("zenquotes", "Cultura e curiosidades", "ZenQuotes · Citação")
def p_zen(ctx: Ctx):
    d = get("https://zenquotes.io/api/random")
    q = d[0]
    if q.get("a") == "zenquotes.io":  # mensagem de limite de uso
        raise RuntimeError(corta(q.get("q"), 80))
    return (f"{corta(q.get('q'), 180)} — {q.get('a')}", {})


@sonda("xkcd", "Cultura e curiosidades", "xkcd · Tirinha mais recente")
def p_xkcd(ctx: Ctx):
    d = get("https://xkcd.com/info.0.json")
    return (f"#{d.get('num')} “{d.get('title')}” — {corta(d.get('alt'), 150)}", {})


@sonda("pokeapi", "Cultura e curiosidades", "PokéAPI · Pokémon do dia (nº = dia do ano)")
def p_pokeapi(ctx: Ctx):
    n = ctx.hoje.timetuple().tm_yday
    d = get(f"https://pokeapi.co/api/v2/pokemon/{n}")
    tipos = ", ".join(t["type"]["name"] for t in d.get("types", []))
    return (f"#{n} {d.get('name')} · tipo {tipos} · {br(d.get('height', 0) / 10, 1)} m · "
            f"{br(d.get('weight', 0) / 10, 1)} kg", {})


@sonda("cocktaildb", "Cultura e curiosidades", "TheCocktailDB · Drink sorteado")
def p_cocktail(ctx: Ctx):
    d = get("https://www.thecocktaildb.com/api/json/v1/1/random.php")
    x = (d.get("drinks") or [None])[0]
    if not x:
        raise LookupError("sem drinks")
    return (f"{x.get('strDrink')} · {x.get('strCategory')} · {x.get('strAlcoholic')} · "
            f"servir em {x.get('strGlass')}", {})


@sonda("uselessfacts", "Cultura e curiosidades", "Useless Facts · Fato aleatório")
def p_uselessfacts(ctx: Ctx):
    d = get("https://uselessfacts.jsph.pl/api/v2/facts/random", {"language": "en"})
    return (corta(d["text"], 200), {})


@sonda("datamuse", "Cultura e curiosidades", "Datamuse · Palavras associadas")
def p_datamuse(ctx: Ctx):
    d = get("https://api.datamuse.com/words", {"ml": "ephemeral", "max": 5})
    palavras = [w["word"] for w in d if "word" in w]
    if not palavras:
        raise LookupError("sem palavras")
    return ("ligadas a 'ephemeral': " + ", ".join(palavras), {})


@sonda("adviceslip", "Cultura e curiosidades", "Advice Slip · Conselho do dia")
def p_advice(ctx: Ctx):
    d = get("https://api.adviceslip.com/advice")
    return (corta(d["slip"]["advice"], 200), {})


# ═════════════════════ FASE 2 · INFRA E TECNOLOGIA ═════════════════════

@sonda("github", "Infra e tecnologia", "GitHub · python/cpython")
def p_github(ctx: Ctx):
    d = get("https://api.github.com/repos/python/cpython",
            headers={"Accept": "application/vnd.github+json"})
    lic = (d.get("license") or {}).get("spdx_id", "n/d")
    return (f"{br(d.get('stargazers_count'), 0)} estrelas · "
            f"{br(d.get('open_issues_count'), 0)} issues/PRs abertos · licença {lic} · "
            f"último push {str(d.get('pushed_at', ''))[:10]}", {})


@sonda("pypi", "Infra e tecnologia", "PyPI · requests")
def p_pypi(ctx: Ctx):
    d = get("https://pypi.org/pypi/requests/json")
    i = d["info"]
    return (f"requests {i.get('version')} — {corta(i.get('summary'), 100)}", {})


@sonda("npm", "Infra e tecnologia", "npm Registry · react")
def p_npm(ctx: Ctx):
    d = get("https://registry.npmjs.org/react/latest")
    return (f"react {d.get('version')} — {corta(d.get('description'), 100)}", {})


@sonda("hackernews", "Infra e tecnologia", "Hacker News · Notícia nº 1")
def p_hn(ctx: Ctx):
    ids = get("https://hacker-news.firebaseio.com/v0/topstories.json")
    if not ids:
        raise LookupError("lista vazia")
    it = get(f"https://hacker-news.firebaseio.com/v0/item/{ids[0]}.json")
    if not it:
        raise LookupError("item vazio")
    return (f"{corta(it.get('title'), 130)} ({it.get('score')} pts, por {it.get('by')})", {})


@sonda("google_dns", "Infra e tecnologia", "Google Public DNS (DoH) · wikipedia.org")
def p_dns(ctx: Ctx):
    d = get("https://dns.google/resolve", {"name": "wikipedia.org", "type": "A"})
    ips = [a["data"] for a in d.get("Answer", []) if a.get("type") == 1]
    if not ips:
        raise LookupError("sem registro A")
    return ("wikipedia.org → " + ", ".join(ips[:3]), {})


@sonda("endoflife", "Infra e tecnologia", "endoflife.date · Python")
def p_eol(ctx: Ctx):
    d = get("https://endoflife.date/api/python.json")
    c = d[0]
    eol = c.get("eol")
    fim = "sem fim de vida definido" if eol is False else f"fim de vida em {eol}"
    return (f"ciclo mais novo: {c.get('cycle')} (última {c.get('latest')}), {fim}", {})


# ═══════════════════════════ CRUZAMENTOS ═══════════════════════════════

def cruzamentos(ctx: Ctx, R: dict[str, Resultado]) -> list[str]:
    def dado(chave: str, campo: str):
        r = R.get(chave)
        return r.dados.get(campo) if (r is not None and r.ok) else None

    L: list[str] = []
    alvo = ctx.moeda_alvo

    fx = [v for v in (dado("awesomeapi", "taxa"), dado("frankfurter", "taxa"),
                      dado("er_api", "taxa")) if v is not None]
    fx_med = None
    if fx:
        fx_med = statistics.median(fx)
        if len(fx) >= 2:
            disp = (max(fx) - min(fx)) / fx_med * 100
            L.append(f"Câmbio USD→{alvo}: mediana de {len(fx)} fontes = {br(fx_med, 4)} "
                     f"(dispersão entre fontes: {br(disp, 2)}%)")
        else:
            L.append(f"Câmbio USD→{alvo}: só 1 fonte respondeu ({br(fx_med, 4)})")

    btc = [v for v in (dado("coinbase", "preco"), dado("kraken", "preco"),
                       dado("coingecko", "preco")) if v is not None]
    btc_med = None
    if btc:
        btc_med = statistics.median(btc)
        if len(btc) >= 2:
            disp = (max(btc) - min(btc)) / btc_med * 100
            L.append(f"Bitcoin: mediana de {len(btc)} corretoras = US$ {br(btc_med, 2)} "
                     f"(dispersão: {br(disp, 3)}%)")
        else:
            L.append(f"Bitcoin: só 1 fonte respondeu (US$ {br(btc_med, 2)})")

    if btc_med is not None and fx_med is not None:
        L.append(f"1 BTC ≈ {br(btc_med * fx_med, 0)} {alvo} "
                 f"(cotação do BTC × câmbio, ambos por consenso)")

    selic_bcb, selic_br = dado("bcb_selic", "valor"), dado("brasilapi_taxas", "selic")
    if selic_bcb is not None and selic_br is not None:
        try:
            ok = abs(float(selic_bcb) - float(selic_br)) < 0.01
            L.append(f"Selic validada em 2 fontes: BCB {br(selic_bcb, 2)}% × BrasilAPI "
                     f"{br(selic_br, 2)}% → {'conferem' if ok else 'DIVERGEM'}")
        except (TypeError, ValueError):
            pass

    rc, wb = dado("restcountries", "populacao"), dado("worldbank", "populacao")
    if rc and wb:
        dif = (rc - wb) / wb * 100
        L.append(f"População de {ctx.pais}: REST Countries {br(rc, 0)} × World Bank "
                 f"{br(wb, 0)} (diferença {br(dif, 2)}%)")

    t_hoje, t_ano = dado("forecast", "tmax"), dado("archive", "tmax")
    if t_hoje is not None and t_ano is not None:
        delta = t_hoje - t_ano
        sinal = "mais quente" if delta > 0 else "mais frio" if delta < 0 else "igual"
        L.append(f"Máxima de hoje em {ctx.nome}: {br(t_hoje)}°C × {br(t_ano)}°C no mesmo dia "
                 f"de um ano atrás → {br(abs(delta))}°C {sinal}")

    dist = dado("iss", "dist_km")
    if dist is not None:
        L.append(f"A ISS está a {br(dist, 0)} km de {ctx.nome} em linha reta "
                 f"(distância de grande círculo na superfície)")

    kp, onda = dado("swpc_kp", "kp"), dado("marine", "onda_m")
    if kp is not None and onda is not None:
        L.append(f"Kp {br(kp, 2)} no espaço e ondas de {br(onda, 2)} m no mar: "
                 f"o céu e a água estão '{'agitados' if kp >= 4 or onda >= 2 else 'tranquilos'}'")

    return L


# ═══════════════════════════ APRESENTAÇÃO ══════════════════════════════

def imprimir(ctx: Ctx, R: dict[str, Resultado], duracao: float,
             cruz: list[str], cor: bool) -> None:
    def c(codigo: str, txt: str) -> str:
        return f"\033[{codigo}m{txt}\033[0m" if cor else txt

    largura = max(60, min(140, shutil.get_terminal_size((100, 20)).columns))
    barra = "═" * largura

    print(c("1;36", barra))
    print(c("1;36", f" ALMANAQUE VIVO · {ctx.titulo_local or ctx.cidade}"))
    print(c("36", f" {ctx.agora:%d/%m/%Y %H:%M} (hora local) · moeda {ctx.moeda} · "
                  f"câmbio USD→{ctx.moeda_alvo}"))
    print(c("1;36", barra))

    for grupo in GRUPOS:
        print("\n" + c("1;33", f"▌ {grupo.upper()}"))
        for s in SONDAS:
            if s.grupo != grupo:
                continue
            r = R.get(s.chave)
            if r is None:
                continue
            marca = c("32", "✔") if r.ok else c("31", "✘")
            print(f"  {marca} {c('1', r.titulo)} {c('90', f'({r.ms} ms)')}")
            corpo = textwrap.fill(r.resumo, width=largura, initial_indent="      ",
                                  subsequent_indent="      ")
            print(c("0", corpo) if r.ok else c("31", corpo))

    if cruz:
        print("\n" + c("1;35", "▌ CRUZAMENTOS (o que as APIs dizem juntas)"))
        for linha in cruz:
            print(textwrap.fill("• " + linha, width=largura, initial_indent="  ",
                                subsequent_indent="    "))

    ok = sum(1 for r in R.values() if r.ok)
    print("\n" + c("1;36", barra))
    print(c("1", f" {ok}/{len(R)} APIs responderam em {duracao:.1f}s"))
    falhas = [r for r in R.values() if not r.ok]
    if falhas:
        print(c("90", " Falhas: " + "; ".join(f"{r.titulo.split(' · ')[0]} ({r.resumo})"
                                              for r in falhas)))
    print(c("1;36", barra))


def preparar_console() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    if os.name == "nt":
        os.system("")  # habilita sequências ANSI no console do Windows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Retrato em tempo real de um lugar usando 50 APIs públicas.")
    ap.add_argument("cidade", nargs="?", default="Fortaleza", help="cidade a consultar (padrão: Fortaleza)")
    ap.add_argument("--json", metavar="ARQUIVO", help="salva o relatório completo em JSON")
    ap.add_argument("--timeout", type=int, default=15, help="timeout por requisição, em segundos (padrão: 15)")
    ap.add_argument("--workers", type=int, default=12, help="consultas simultâneas (padrão: 12)")
    ap.add_argument("--listar", action="store_true", help="lista as 50 APIs e sai")
    args = ap.parse_args(argv)

    preparar_console()

    chaves = [s.chave for s in SONDAS]
    if len(SONDAS) != 50 or len(set(chaves)) != 50:
        raise AssertionError(f"esperadas 50 sondas únicas, encontradas {len(SONDAS)}")

    if args.listar:
        for i, s in enumerate(SONDAS, 1):
            print(f"{i:>2}. [{s.grupo}] {s.titulo}")
        return 0

    CONFIG["timeout"] = max(1, args.timeout)
    cor = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    ctx = Ctx(cidade=args.cidade.strip())
    if not ctx.cidade:
        print("Informe o nome de uma cidade.", file=sys.stderr)
        return 2

    t0 = time.perf_counter()
    R: dict[str, Resultado] = {}

    # Fase 1: sequencial, pois cada passo alimenta o contexto do seguinte.
    for s in (x for x in SONDAS if x.fase == 1):
        r = executar(s, ctx)
        R[s.chave] = r
        if s.chave == "geocoding" and not r.ok:
            print(f"Não foi possível localizar {ctx.cidade!r}: {r.resumo}", file=sys.stderr)
            return 1

    # Fase 2: paralela, já com coordenadas, país, fuso, moeda e data local.
    fase2 = [x for x in SONDAS if x.fase == 2]
    print(f"Consultando {len(fase2)} APIs em paralelo para {ctx.titulo_local}…", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        for r in ex.map(lambda sd: executar(sd, ctx), fase2):
            R[r.chave] = r

    duracao = time.perf_counter() - t0
    cruz = cruzamentos(ctx, R)
    imprimir(ctx, R, duracao, cruz, cor)

    if args.json:
        try:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump({
                    "gerado_em": datetime.now(timezone.utc).isoformat(),
                    "local": {"nome": ctx.nome, "regiao": ctx.regiao, "pais": ctx.pais,
                              "lat": ctx.lat, "lon": ctx.lon, "fuso": ctx.tz,
                              "moeda": ctx.moeda},
                    "cruzamentos": cruz,
                    "resultados": [asdict(R[s.chave]) for s in SONDAS if s.chave in R],
                }, f, ensure_ascii=False, indent=2, default=str)
            print(f"\nRelatório salvo em {args.json}", file=sys.stderr)
        except OSError as e:
            print(f"\nNão foi possível salvar o JSON: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
