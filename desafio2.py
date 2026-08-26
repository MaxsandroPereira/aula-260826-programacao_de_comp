#faça uma calculadora com as quatro operações matemáticas básicas.

num1 = float(input("primeiro número: "))
num2 = float(input("segundo número: "))

soma = num1 + num2
subtracao = num1 - num2
divisao = num1 / num2
multiplicacao = num1 * num2

print("escolha a operação matemática que deseja realizar: ")
print("1 - Soma")
print("2 - Subtração")
print("3 - Divisão")
print("4 - Multiplicação")

opcao = int(input("Digite a opção desejada: "))
if opcao == 1:
    print("O resultado da soma é: ", soma)

if opcao == 2:
    print("o resultado da subtração é: ", subtracao)

if opcao == 3:
    print("o resultado da divisao é: ", divisao)

if opcao == 4:
    print("o resultado da multiplicação é: ", multiplicacao)

