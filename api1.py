try:
    import requests
except ModuleNotFoundError:
    raise SystemExit("Instale o pacote 'requests' antes de executar este script: pip install requests")

ingrediente = input("Digite um ingrediente: ")

url = "https://api.spoonacular.com/recipes/complexSearch"

parametros = {
    "apiKey": "SUA_API_KEY",
    "query": ingrediente,
    "number": 3
}

resposta = requests.get(
    url,
    params=parametros
).json()

print("\nRECEITAS ENCONTRADAS")

for receita in resposta.get("results", []):

    print(f"Nome: {receita['title']}")
    print(f"ID: {receita['id']}")
    print()