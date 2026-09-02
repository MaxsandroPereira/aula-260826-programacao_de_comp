# utf-8

# created on 02.09.26

# @author: Maxsandro

produtos = []
preços = []

for i in range(5):

    produto = input(f"Digite o nome do produto {i + 1}: ")

    while True:
        try:
            preço = float(input(f"Digite o preço do produto {i + 1}: "))
            break
        except ValueError:
            print("Valor inválido! Favor Digitar apenas números.")

    produtos.append(produto)
    preços.append(preço)


total = sum(preços)

maiorpreco = max(preços)
menorpreco = min(preços)

maiorindice = preços.index(maiorpreco)
menorindice = preços.index(menorpreco)


# Linhas para separar
print()
print()
print()

print("Você comprou os seguintes produtos:")

for i in range(len(produtos)):
    print(f"- {produtos[i]}: R${preços[i]:.2f}")

print("Seu Total gasto foi de: R$", total)
print("O produto mais caro:", produtos[maiorindice], "R$", maiorpreco)
print("O produto mais barato:", produtos[menorindice], "R$", menorpreco)