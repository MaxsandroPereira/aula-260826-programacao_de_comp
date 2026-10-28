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


