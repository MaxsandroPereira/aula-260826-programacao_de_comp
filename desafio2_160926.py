# O desafio consiste em criar um pequeno programa
# que utilize 5 APIs, sem usar aquelas mais básicas
# que já foram utilizadas em sala de aula.

# Projeto: Assistente Culinário

# Instale a dependência com: pip install requests

import requests
from urllib.parse import urlparse


class _Response:
    def __init__(self, body, status_code):
        self._body = body
        self.status_code = status_code

    def json(self):
        try:
            return self._body
        except Exception:
            return {}


class _Requests:
    # Somente os domínios necessários para as cinco APIs deste projeto.
    HOSTS_PERMITIDOS = {
        "www.themealdb.com",
        "world.openfoodfacts.org",
        "en.wikipedia.org",
        "www.thecocktaildb.com",
        "openlibrary.org",
    }

    @staticmethod
    def get(url, params=None):
        try:
            parsed = urlparse(url)

            # Bloqueia esquemas como file:// e http://.
            if parsed.scheme != "https":
                raise ValueError("Somente URLs HTTPS são permitidas")

            # Bloqueia hosts fora da lista autorizada.
            if not parsed.hostname or parsed.hostname.lower() not in _Requests.HOSTS_PERMITIDOS:
                raise ValueError("Host não autorizado")

            # Evita credenciais embutidas na URL.
            if parsed.username or parsed.password:
                raise ValueError("Credenciais embutidas na URL não são permitidas")

            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": "aulapython-culinary-assistant"},
                timeout=15,
                allow_redirects=False,
            )

            try:
                body = response.json()
            except ValueError:
                body = {}

            return _Response(body, response.status_code)

        except (requests.RequestException, ValueError):
            return _Response({}, 0)


requests_api = _Requests()

ingrediente = input("Digite um ingrediente (em inglês): ").strip()

print("\nProcurando receitas e informações...")
print("=" * 45)


# 1. THE MEAL DB
# Procura uma receita que utilize o ingrediente informado.
url = "https://www.themealdb.com/api/json/v1/1/filter.php"
parametros = {"i": ingrediente}
resposta = requests_api.get(url, params=parametros).json()

print("\nRECEITAS ENCONTRADAS")
if resposta.get("meals"):
    receita = resposta["meals"][0]
    print(f"Prato: {receita['strMeal']}")
    print(f"Imagem: {receita['strMealThumb']}")
else:
    print("Não encontrei nenhuma receita.")


# 2. OPEN FOOD FACTS
# Busca informações nutricionais de um produto relacionado ao ingrediente.
url = "https://world.openfoodfacts.org/api/v2/search"