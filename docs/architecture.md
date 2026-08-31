# Arquitetura e limites

O pipeline é `source -> document -> chunk -> análise -> memória/fato/traço -> embedding`. Cada entidade derivada carrega `source_id`; a exclusão de fonte percorre essa relação. Para exportações de conversa, o usuário informa o rótulo da pessoa-alvo. Somente as mensagens desse rótulo são usadas para aprender fatos, opiniões e estilo; falas de terceiros são contexto do par pergunta/resposta. O analisador só cria fatos quando há enunciados explícitos e marca padrões como `INFERENCE` com evidências. Ausência de evidência é `UNKNOWN`.

O cliente de LLM é intercambiável via uma interface. A implementação atual chama a API local compatível com Ollama. Os embeddings usam uma projeção hash determinística local para manter a primeira versão totalmente executável sem downloads; substitua `EmbeddingService` por um modelo local de sentence-transformers quando desejado, preservando a mesma interface.
