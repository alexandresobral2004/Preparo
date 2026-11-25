# Previsão de colheita e gerenciamento do Preparo

Este guia explica, em linguagem simples, como o sistema prevê quantos litros há numa panela e em que horário ela deve ser retirada, e como o app organiza os preparos, os blocos, as panelas e os alertas.

---

## 1. Visão geral

Um **preparo** é um dia (ou uma sessão) de cozimento. Dentro dele há **registros**, cada um com **blocos** de até 5 panelas. Cada **panela** passa por etapas:

```
vazia → no fogo (tem horário de entrada) → fervendo (tem horário de fervura) → colhida (tem horário e litros da colheita)
```

O sistema usa as panelas **já colhidas** do histórico para aprender como o líquido evapora. Com esse aprendizado, ele estima:

- quantos litros há na panela **agora**;
- quantos litros haverá após **X minutos de fervura**;
- em que **horário** a panela atinge a meta. A meta é a **meta padrão do preparo** (10,15 L de fábrica), que **qualquer usuário com permissão de editar** pode alterar (ver seção 8.6).

> **Ideia central:** a previsão é uma linha reta. Começa em um volume inicial, que depende do peso da panela, e perde litros a uma taxa constante por minuto de fervura. O sistema aprende o volume inicial e a taxa com os seus preparos anteriores.

---

## 2. Os dados que alimentam a previsão

| Campo | O que é | Para que serve |
|---|---|---|
| `tipo` | `1ª vez`, `2ª vez`, `3ª vez` ou `APURO` | Cada tipo tem um ponto de partida diferente |
| `pesoSecaKg` | Peso da panela vazia (kg) | Base para o cálculo |
| `pesoCheiaKg` | Peso da panela com mariri e chacrona (kg) | Com a seca, dá o **peso líquido inicial** (`cheia − seca`) |
| `pesoComAguaKg` | Peso com água (kg), opcional | Dá a **água adicionada** (`comÁgua − cheia`) |
| `entrada` | Horário em que a panela foi ao fogo | Início do cozimento |
| `fervura` | Horário em que começou a ferver | Início do tempo de fervura (base da previsão) |
| `colhida` | Horário da colheita | Fecha a panela e entra no histórico |
| `litros` | Litros colhidos de fato | É a informação que o modelo aprende |
| `metaLitros` | Meta desta panela (opcional) | Se vazio, usa a **meta padrão do preparo** (variável `metaLitrosPadrao`, ver seção 8.6) |

**Regra de ouro:** sem peso, o sistema não tem como calcular o volume inicial com precisão. Ele ainda estima, mas com um aviso e uma margem bem maior.

---

## 3. Como a previsão funciona, passo a passo

### 3.1 O volume inicial

Para uma panela com pesos informados, o volume inicial é:

```
V0 = β0 + β_Δp · Δp + β_seca · seca + γ_tipo  (+ β_água · (água − média), se houver água)
```

- **Δp** = peso líquido = `cheia − seca`, em kg (≈ litros, pois 1 kg de água ≈ 1 L);
- **γ_tipo** é um ajuste por tipo de panela (só quando há dados suficientes);
- **β** são coeficientes aprendidos com o histórico.

Enquanto não há histórico, os coeficientes vêm de um **prior físico** por tipo. Ou seja, um chute informado:

| Tipo | Fator inicial (L por kg de líquido) | Taxa de evaporação inicial |
|---|---|---|
| 1ª vez | 0,72 | 2,4 L/h |
| 2ª vez | 0,80 | 2,5 L/h |
| 3ª vez | 0,85 | 2,6 L/h |
| APURO | 0,98 | 3,0 L/h |

Tipos não reconhecidos usam 0,80 e 2,5 L/h.

### 3.2 A taxa de evaporação

Depois de começar a fervura, o volume cai a uma **taxa constante** `r` (litros por minuto):

```
V(t) = V0 − r · t        (t = minutos de fervura)
```

A taxa é limitada a um intervalo plausível: entre 0,3 L/h e 30 L/h.

### 3.3 O horário de colheita

Quando a panela chega à meta `M`:

```
t_alvo = (V0 − M) / r
```

O horário previsto é `horário da fervura + t_alvo`.

### 3.4 Exemplo com números

Uma panela de **2ª vez**, com seca de 12 kg e cheia de 32 kg:

1. Δp = 32 − 12 = **20 kg** (≈ 20 L de líquido inicial)
2. V0 = 0,80 × 20 = **16 L** (prior de 2ª vez)
3. Taxa = 2,5 L/h = **0,0417 L/min**
4. Tempo até 10,15 L = (16 − 10,15) / 0,0417 ≈ **140 min** (2 h 20 min)
5. Se a fervura começou às 23:10, a retirada prevista é **01:30**.

Com 60 min de fervura, a previsão de litros agora é 16 − 0,0417 × 60 ≈ **13,5 L**.

---

## 4. As camadas do modelo: o sistema aprende aos poucos

O sistema escolhe automaticamente a estatística mais forte que os dados permitem. O nível aparece no app como um selo:

| Nível (selo) | Quando acontece | O que muda |
|---|---|---|
| **Calibração inicial** | Menos de 2 panelas pesadas e colhidas | Usa só os priors físicos |
| **Aprendendo** | 2 a 5 panelas pesadas (ou, sem pesos, 2+ tempos de colheita) | Estimativa bayesiana: mistura o prior com os dados (quanto mais dado, menos o prior pesa) |
| **Modelo calibrado** | 6 ou mais panelas pesadas e colhidas | Regressão ridge com restrições físicas e robustez a outliers (método Huber) |

Dentro do modelo calibrado, quando há **6 ou mais panelas com água informada**, a água entra como variável. Antes disso, ela é ignorada: o sistema nunca trata "não informado" como "zero litros".

### 4.1 Sem pesos

Se a panela não tem pesos, mas há ao menos 2 colheitas com tempo e litros, o sistema usa a **mediana** do histórico do mesmo tipo (ou geral) para estimar o tempo até a meta. A margem é fixa e maior: ±2,5 L e ±25 min.

### 4.2 Quais panelas entram no aprendizado

Uma colheita só vira amostra se:

- tiver horário de fervura e de colheita, e litros maiores que zero;
- o tempo de fervura estiver entre 1 min e 16 h;
- o registro não estiver excluído.

---

## 5. O fator de fornalha: adaptando ao fogo do dia

As 5 panelas de um bloco são aquecidas pela mesma fornalha, mas nem sempre recebem o mesmo calor. Uma pode ferver primeiro porque está mais perto do fogo ou porque a lenha caiu nela.

O sistema usa as **panelas já colhidas do mesmo bloco** para medir isso:

1. Para cada panela colhida, compara o **tempo real** de fervura com o **tempo que o modelo previa** para tirar os mesmos litros. Por exemplo, se o modelo previa 120 min e ela levou 90 min, a razão é 0,75.
2. Combina essas razões em média geométrica, **encolhida para 1** (fogo normal). Com poucas panelas, o ajuste é pequeno; com mais, cresce.
3. Limita o resultado entre **0,6** (fogo muito forte) e **1,6** (fogo muito fraco).

Com o fator `f` aplicado:

- o tempo até a meta passa a ser `t_alvo × f`;
- o volume em um instante `t` é calculado no tempo `t / f`.

Se `f = 0,8`, o fogo está 20% mais rápido que o modelo, e a previsão antecipa a retirada.

> **Limite:** o fator só existe quando há panelas colhidas no mesmo bloco, na mesma requisição. Antes da primeira colheita, o fator é 1.

---

## 6. O que a tela mostra

### 6.1 Campos da previsão

| Campo | Significado |
|---|---|
| **Volume estimado agora** | Litros previstos no instante atual, com a margem (±) |
| **Ponto para X L** | Horário previsto de retirada e tempo restante |
| **Progresso** | Quanto do caminho entre o volume inicial e a meta já foi percorrido |
| **Taxa** | Litros evaporados por hora (já corrigida pelo fator de fornalha) |
| **Margem ±min** | Erro esperado no horário |
| **Com fervura de…** | Projeção em marcos de 30 min (30 min, 1 h, 1 h 30…) com os litros previstos |

### 6.2 Como ler a margem de erro

A margem de litros é `1,25 × erro médio absoluto` do modelo, com mínimo de 0,5 L. Com o modelo ainda em calibração inicial, ela é de 12% do volume inicial (mínimo 1,2 L). A margem de minutos segue a mesma lógica, com mínimo de 5 min.

### 6.3 Estados especiais

- **Aguardando fervura:** a panela está no fogo, mas sem horário de fervura. O sistema mostra o volume inicial e o tempo previsto de fervura, e pede para marcar a fervura.
- **Passou do ponto:** o tempo de fervura já ultrapassou o horário previsto para a meta.
- **Sem dados suficientes:** a panela não tem pesos nem histórico utilizável. Aparece a mensagem pedindo peso e horário.

---

## 7. Alertas de preenchimento

Os alertas aparecem em duas cores:

- **Faltando (vermelho):** dado obrigatório ausente ou inconsistente. Exemplos: panela sem tipo; colheita sem fervura; litros sem horário de colheita; peso com água menor que o peso cheio.
- **Conferir (amarelo):** possível esquecimento, que depende de dois limites configuráveis:
  - **Sem fervura após X min da entrada** (padrão do banco local: 60 min);
  - **Sem colheita após X h da entrada** (padrão do banco local: 2 h).

Esses limites e a meta padrão são configurados por preparo, no botão de configurações da tela de Andamento.

---

## 8. Gerenciamento

### 8.1 Preparos e membros

- Cada usuário pode ter vários **preparos**. Há um preparo **ativo** por vez.
- O **dono** cria o preparo, aprova ou recusa pedidos e define quem pode editar.
- Quem quer participar **solicita** entrada. O pedido fica **pendente** até o dono aprovar.
- Cada membro aprovado tem uma **permissão**:
  - **editar:** registra e altera panelas, blocos e registros;
  - **acompanhar:** vê a tela e a previsão, mas as rotas de gravação respondem com erro 403. A permissão é conferida no banco a cada requisição, então uma mudança vale imediatamente.
- O dono nunca é rebaixado por um convite.

### 8.2 Registros, blocos e panelas

- Um **registro** é o dia de um preparo. Ele tem blocos, e cada bloco tem até 5 panelas.
- As panelas são numeradas automaticamente (bloco 1: 1 a 5; bloco 2: 6 a 10…).
- Registros podem ser **excluídos** (a exclusão é lógica: o dado fica no banco e sai das estatísticas).
- Há exportação em **CSV** e **JSON**, e importação de arquivo.

### 8.3 Rascunho automático

O que é digitado é salvo como rascunho, no navegador e no servidor (tabela `rascunhos`, por preparo). Se a tela for fechada, o trabalho não se perde. Se outra pessoa alterar o preparo enquanto você edita, o servidor responde com conflito (HTTP 409) e a tela recarrega a versão mais recente. O rascunho do servidor é removido pela rota `DELETE /api/rascunho`.

### 8.4 Lembretes

Lembretes simples (texto + horário + "feito"), úteis para não esquecer de conferir lenha ou de retirar uma panela.

### 8.6 Configurações do preparo (inclui a meta padrão)

As configurações do preparo ficam na tela de Andamento e valem para **todos os membros** daquele preparo. Elas são:

| Variável | Para que serve | Valor inicial (preparo novo) |
|---|---|---|
| `metaLitrosPadrao` | **Meta padrão de litros** de cada panela, usada quando a panela não tem meta própria | 10,15 L |
| `minSemFervura` | Minutos após a entrada para alertar "sem fervura" | 30 min |
| `horasSemColheita` | Horas após a entrada para alertar "sem colheita" | 5 h |

> **Quem pode alterar a meta padrão:** a alteração **não é restrita ao dono**. Qualquer usuário com **permissão de editar** no preparo pode mudar a meta padrão. Isso inclui o dono e os membros aprovados com permissão *editar*. Um membro com permissão *acompanhar* não consegue alterá-la: a gravação responde com erro 403.
>
> Por ser uma configuração compartilhada, uma mudança feita por um editor afeta as previsões de todos os membros do preparo, a partir da próxima atualização da tela.

> **Como o valor inicial chega ao preparo:** ao criar um preparo, cada variável é copiada da configuração global do sistema (`configuracoes`), cujo valor de fábrica é o da tabela. Depois disso, cada preparo tem a sua própria cópia, que pode ser alterada sem afetar os outros. No banco local, a configuração global já foi alterada (meta 15,0 L, alerta de colheita em 2 h), então preparos criados ali começam com esses valores. Confira sempre o valor em uso na tela de Andamento.

### 8.5 Contas e segurança

- Login com usuário ou e-mail e senha. Há limite de tentativas erradas por 15 minutos.
- Cadastro por e-mail com validação; o perfil guarda nome e e-mail.
- Perfis de sistema: **admin** (gerencia usuários) e **usuário comum**.
- Sessões têm token; o banco guarda só o hash do token.

---

## 9. Boas práticas para a previsão ficar boa

1. **Pese sempre** a panela vazia e a cheia. É o dado que mais melhora a previsão.
2. **Marque a fervura no momento certo.** Ela é o ponto de partida de toda estimativa.
3. **Registre a colheita com litros reais.** Cada colheita bem registrada é uma amostra para o modelo aprender.
4. **Não apague colheitas erradas sem corrigir.** Uma colheita com litros errados desloca a calibração.
5. **Informe a água** quando possível: com 6 amostras, ela passa a ser usada.
6. **Confira os alertas amarelos.** Panela sem colheita há muitas horas costuma ser esquecimento.

---

## 10. Limitações conhecidas

- **Não há leitura de litros durante o cozimento.** A previsão só é corrigida pelas panelas já colhidas do mesmo bloco, e não por medições da própria panela.
- **Lenha não é medida.** O fator de fornalha capta o efeito do fogo pelas colheitas, não pela quantidade de lenha.
- **Posição da panela não entra no modelo.** A posição (1 a 5) ainda não é aprendida entre preparos.
- **A taxa é constante.** Na prática, a evaporação pode variar ao longo da fervura. O modelo é uma aproximação linear.
- **Histórico curto dá margem larga.** Nos primeiros preparos, a margem de erro é grande, e isso é esperado.

---

## 11. Onde está cada parte no código

| Assunto | Arquivo |
|---|---|
| Modelo, camadas, previsão por panela, fator de fornalha, projeção | `backend/app/stats.py` |
| Endpoint de previsão | `backend/app/routers/stats.py` |
| Estados da panela e alertas | `backend/app/domain.py` |
| Permissões de membros | `backend/app/preparos.py`, `backend/app/routers/preparos.py` |
| Login e senhas | `backend/app/auth.py` |
| Tela da previsão | `frontend/src/components/PredictionPanel.tsx` |
| Testes do modelo | `backend/tests/test_stats.py` |
