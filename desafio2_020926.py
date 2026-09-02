#desafio 2 = delcarar 5 variaveis maxnota minnota medianota aprovados e reprovados dentro de um range for i in range(10)
#fazer input para declarar o valor de cada nota. com um while no final

maxnota = 0
minnota = 10
medianota = 0
aprovados = 0
reprovados = 0

for i in range(10):
    nota = float(input(f"Digite a nota {i + 1}: "))

    if nota > maxnota:
        maxnota = nota

    if nota < minnota:
        minnota = nota

    medianota += nota

    if nota >= 7:
        aprovados += 1
    else:
        reprovados += 1

media = medianota / 10

print("Maior nota:", maxnota)
print("Menor nota:", minnota)
print("Média das notas:", media)
print("Quantidade de aprovados:", aprovados)
print("Quantidade de reprovados:", reprovados)