# Estudo Adaptativo BB — atualização v0.9

A v0.9 contém as cinco abas acordadas, na ordem **Desempenho · Cards · Caderno de erros · Questões Inéditas · Configurações**.

- **Desempenho:** percentual de acertos e faixa de incerteza Wilson 95% por matéria usando somente os registros declarados em Questões Inéditas. Por assunto, exibe evidências separadas dos Cards e dos links do Caderno de erros. **Não atribui inéditas a assuntos.** Sem histórico, os percentuais ficam vazios.
- **Questões Inéditas:** informe data, matéria, total de questões feitas e acertos; salve, edite, exclua e restaure registros sem preencher assuntos.
- **Domínio:** meta de pelo menos 90% nos resultados distintos do Caderno, sem chutes, mais confirmações de recuperação espaçada, conceito e explicação. Essa métrica não é garantia de 90% em questões inéditas por assunto.
- **Prioridade:** soma até 6 pontos por oportunidade observada nos assuntos com erros, conservando fórmula-base, priorização de manutenção vencida e separação por matéria.
- **Risco:** correção conservadora com no mínimo 12 observações e auditoria retrospectiva, com pontuação Brier divulgada pela API somente após 20 observações; sem pretender probabilidade calibrada.
- **Exclusões:** sem matriz de edital, sem orientação automática de como resolver questões, sem peso de prova, sem cronômetro nem metas diárias obrigatórias.

## Instalação no seu repositório

**O conector do GitHub recusou escrita (403)**. Por isso este arquivo é um **pacote de atualização** e não um commit feito no GitHub. O instalador exige um clone do código da v0.8; não execute contra outra versão sem revisar as diferenças.

1. Extraia este ZIP em uma pasta à parte. Abra um terminal na **raiz do seu clone** `estudo-adaptativo` na versão v0.8.
2. Rode, ajustando o caminho do arquivo extraído:

   ```powershell
   python "C:\caminho\estudo-adaptativo-v0.9\aplicar_v09.py"
   python -m pip install -e ".[dev]"
   python -m pytest -q
   ```

3. Confira os resultados e as alterações:

   ```powershell
   git diff --stat
   git status
   ```

4. Se os testes passarem, faça backup do banco Neon e publique as mudanças:

   ```powershell
   git add .gitignore README.md app migrations tests scripts
   git commit -m "feat: estudo adaptativo v0.9 - desempenho e ineditas"
   git push origin master
   ```

5. O serviço Render conectado à `master` pode iniciar deploy automaticamente. A configuração existente executa `alembic upgrade head` antes de subir o FastAPI. Confirme que a migration `0007` ocorreu e o deploy está **Live** antes de testar a versão publicada.

A migração `0007_novel_practice` **só acrescenta** uma tabela e um índice. Não apaga nem substitui histórico de Cards ou Caderno de erros. O código fonte preexistente é preservado em backups `*.v08.bak` locais, ignorados no `.gitignore`; não os publique.

## Validação

Foram verificados localmente: sintaxe Python do instalador e dos três arquivos novos; sintaxe JS dos novos blocos; e a presença dos principais pontos de inserção na v0.8 do GitHub. **Não foi possível executar a suíte `pytest` contra o repositório completo nem testar o deploy**, pois a conexão permitiu leitura, mas não o checkout/publicação automática.

## Arquivos deste pacote

- `aplicar_v09.py`: aplica as alterações aos arquivos existentes e instala os novos.
- `app/performance.py`: agregação de inéditas e indicadores por assunto, mantendo os grupos separados.
- `migrations/versions/0007_novel_practice.py`: migração aditiva de banco.
- `tests/test_performance_v9.py`: novos testes de persistência, edição, separação de métricas, auditoria e interface.
