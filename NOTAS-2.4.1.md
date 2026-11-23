# Ripagem Maker 2.4.1

XMLs recebem nomes com produto/origem, tipo de entrega, data e versão sequencial. Exemplo:

`P Protect para SizeFix - Troca de potes - 2026-10-27 - V01.xml`

Novas exportações no mesmo dia recebem V02, V03 etc. Arquivos antigos não são renomeados ou sobrescritos; projetos já importados continuam com suas referências.

O nome da sequência no Premiere acompanha o nome do XML. O relatório JSON da montagem usa a mesma base. O padrão também cobre trocas de ML, takes visuais, marcadores e cortes.

Nomes são compatíveis com Mac e Windows. Exportações simultâneas reservam versões diferentes. Os testes verificam segurança de caminhos, nomes acentuados, limites de tamanho, preservação dos arquivos e correspondência do nome da sequência.
