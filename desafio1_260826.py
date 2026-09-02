
#faça um sistema de média, aplicando duas notas e exibindo o valor da média. Também diga 
#se o aluno está reprovado, em recuperação ou aprovado.


maxnota = 0
minnota = 0

# /////////////////////////////////////////////////////

print("##Sistema de média através das notas##")
nota1 =float(input("Digite a primeira nota: "))
nota2 = float(input("Digite a segunda nota: "))

media = (nota1 + nota2)/2

print("sua média é",media)

if media >= 7 : 
    print ("Você está aprovado. Parabéns!")
if media >= 5 and media < 7:
    print ("Sua nota está abaixo da média. Precisará fazer a prova final.")

if media < 5: 
    print ("Você está reprovado.")

print("Deseja continuar calculando?")
resposta = input("s/n: ")

resposta = "s"

while resposta == "s":

    nota1 = float(input("Digite a primeira nota: "))
    nota2 = float(input("Digite a segunda nota: "))

    media = (nota1 + nota2) / 2

    print("Sua média é", media)

    if media >= 7:
        print("Você está aprovado. Parabéns!")

    elif media >= 5:
        print("Sua nota está abaixo da média. Precisará fazer a prova final.")

    else:
        print("Você está reprovado.")

    print("Deseja continuar calculando?")
    resposta = input("s/n: ")

print("Programa encerrado.")


#desafio concluido