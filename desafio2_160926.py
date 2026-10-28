# O desafio consiste em criar um pequeno programa
# que utilize 5 APIs, sem usar aquelas mais básicas
# que já foram utilizadas em sala de aula.

# Projeto: Assistente Culinário

# pip install requests

import json

from urllib.parse import urlencode
from urllib.request import Request, urlopen


class _Response:

    def __init__(self, body, status_code):
        self._body = body
        self.status_code = status_code

    def json(self):
        return json.loads(self._body)


class _Requests:

    @staticmethod
    def get(url, params=None):

        if params:
            url = f"{url}?{urlencode(params)}"

        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "aulapython-culinary-assistant"
                }
            )

            with urlopen(request, timeout=15) as response:
                return _Response(
                    response.read().decode("utf-8"),
                    response.status
                )

        except Exception:
            return _Response("{}", 0)


requests = _Requests()

ingrediente = input(
    "Digite um ingrediente (em inglês): "
)

print("\nProcurando receitas e informações...")
print("=" * 45)


# 1. THE MEAL DB
# Aqui eu procuro uma receita que utilize
# o ingrediente que o usuário informou.

url = "https://www.themealdb.com/api/json/v1/1/filter.php"

parametros = {
    "i": ingrediente
}

resposta = requests.get(
    url,
    params=parametros
).json()

print("\nRECEITAS ENCONTRADAS")

if resposta.get("meals"):

    receita = resposta["meals"][0]

    print(f"Prato: {receita['strMeal']}")
    print(f"Imagem: {receita['strMealThumb']}")

else:
    print("Não encontrei nenhuma receita.")


# 2. OPEN FOOD FACTS
# Agora eu tento encontrar informações
# nutricionais de um produto relacionado
# ao ingrediente escolhido.

# 2. OPEN FOOD FACTS
# Buscando informações nutricionais
# de um produto relacionado ao ingrediente.

url = "https://world.openfoodfacts.org/api/v2/search"

parametros = {
    "search_terms": ingrediente,
    "page_size": 5,
    "fields": "product_name,nutriments"
}

resposta = requests.get(
    url,
    params=parametros
).json()

print("\nINFORMAÇÕES NUTRICIONAIS")

if resposta.get("products"):

    produto = resposta["products"][0]

    nome = produto.get(
        "product_name",
        "Produto desconhecido"
    )

    nutrientes = produto.get("nutriments", {})

    print(f"Produto: {nome}")

    print(
        f"Calorias: "
        f"{nutrientes.get('energy-kcal_100g', 'N/A')} "
        f"kcal/100g"
    )

    print(
        f"Proteínas: "
        f"{nutrientes.get('proteins_100g', 'N/A')} "
        f"g/100g"
    )

else:
    print("Não encontrei informações nutricionais.")

# 3. WIKIPEDIA
# Nesta parte, busco um pouco da história
# e informações sobre o ingrediente escolhido.

titulo = ingrediente.replace(" ", "_")

url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{titulo}"

resposta = requests.get(url)

print("\nUM POUCO SOBRE O INGREDIENTE")

if resposta.status_code == 200:

    dados = resposta.json()

    print(
        dados.get(
            "extract",
            "Resumo não encontrado."
        )
    )

else:
    print("Não encontrei informações sobre esse ingrediente.")


# 4. THE COCKTAIL DB
# Para complementar a experiência culinária,
# escolho uma bebida que pode acompanhar
# o prato.

url = "https://www.thecocktaildb.com/api/json/v1/1/random.php"

resposta = requests.get(url).json()

print("\nSUGESTÃO DE BEBIDA")

if resposta.get("drinks"):

    bebida = resposta["drinks"][0]

    print(f"Nome: {bebida['strDrink']}")
    print(
        f"Categoria: "
        f"{bebida.get('strCategory', 'Não informada')}"
    )

else:
    print("Não consegui encontrar uma bebida.")


# 5. OPEN LIBRARY
# Por último, procuro um livro de culinária
# relacionado ao ingrediente pesquisado.

url = "https://openlibrary.org/search.json"

parametros = {
    "q": f"{ingrediente} cooking",
    "limit": 1
}

resposta = requests.get(
    url,
    params=parametros
).json()

print("\nLIVRO DE CULINÁRIA")

if resposta.get("docs"):

    livro = resposta["docs"][0]

    print(
        f"Título: "
        f"{livro.get('title', 'Desconhecido')}"
    )

    print(
        f"Autor: "
        f"{livro.get('author_name', ['Desconhecido'])[0]}"
    )

else:
    print("Não encontrei nenhum livro relacionado.")


print("\n" + "=" * 45)
print("Pesquisa finalizada! Faça bom proveito!")