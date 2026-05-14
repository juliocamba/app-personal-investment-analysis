# Avaliação de alternativas gratuitas à FMP para uma app pessoal de análise de investimentos

## Síntese executiva

Para o teu caso — app pessoal privada, pipeline diário, foco em empresas dos EUA, análise fundamental e valuation — a melhor solução gratuita não é substituir a FMP por um único provider. A combinação mais sólida é manter a FMP onde ela já funciona, usar urlSEC EDGAR / data.sec.govturn35view1 como fallback principal de fundamentals e urlTwelve Dataturn45search3 como fallback principal de preço EOD. urlFinnhubturn45search1 faz sentido como camada opcional/terciária. Pelo contrário, urlAlpha Vantageturn45search2 free é demasiado limitado e tem termos pouco confortáveis para um produto de análise; e urlyfinanceturn4search0, apesar de útil para protótipos, continua a ser um wrapper não oficial e explicitamente orientado a research/educational purposes. citeturn35view1turn36view3turn11view0turn13search3turn15view1turn31search0turn37view0turn19search0turn17view0turn4search0turn6search0

A conclusão prática é que uma fase apenas de “data availability status” tem pouco valor se não vier acompanhada de fallback real. O passo com mais retorno é implementar primeiro o fallback SEC para statements e depois o fallback de preço; só depois faz sentido aperfeiçoar estados de UI e diagnósticos. Em paralelo, eu deixaria de aprovar automaticamente empresas que não passem num preflight mínimo de cobertura para analysis-grade data. citeturn35view1turn36view3turn13search3turn15view1turn37view0turn46search0

Em resumo: **SEC para fundamentals oficiais dos EUA; Twelve Data para preço; Finnhub apenas como apoio; evitar Alpha Vantage free e yfinance como base principal do pipeline.** citeturn36view3turn13search3turn15view1turn28search0turn37view0turn19search0turn22view0turn4search0turn6search0

## Tabela comparativa

| Provider | Tipo de dados | Free tier | Limites | Cobertura | Fiabilidade | Dificuldade de integração | Adequação para valuation | Riscos / limitações |
|---|---|---|---|---|---|---|---|---|
| urlSEC EDGAR / data.sec.govturn35view1 | Filings e XBRL `companyfacts/companyconcept/frames`; **sem preço** | Sem custo | Fair access: 10 req/s; `User-Agent` obrigatório | Empresas que reportam à SEC | Muito alta para fundamentals; a própria SEC lembra que datasets não substituem filings | Média/alta | **Excelente** para `statements_norm`; insuficiente sozinho por faltar preço | Sem cotação; taxonomias custom; units/períodos exigem normalização própria. citeturn35view1turn36view1turn36view3turn36view0 |
| urlAlpha Vantageturn45search2 | Preços, statements, shares outstanding, indicadores | Free disponível | 25 requests/dia free; histórico diário full premium; `TIME_SERIES_DAILY_ADJUSTED` premium; premium desde 75 req/min | Global equities + fundamentals | Boa como API comercial; free muito condicionado | Baixa | **Fraca** no teu caso free | Termos classificam investment analysis/research/testing/monitoring como “commercial use”; free demasiado curto. citeturn19search0turn22view2turn22view0turn20search0turn23view0turn22view4turn22view5turn22view1turn17view0 |
| urlTwelve Dataturn45search3 | Preços, perfil, actions, statements e outros fundamentals | Basic gratuito | 8 API credits/min e 800/dia; `time_series` pesa 1 crédito; `income_statement` pesa 100 por símbolo; 3 mercados no Basic | EUA + outros mercados/trial conforme plano | Boa para analytics; caveat de feed US default | Baixa/média | **Melhor fallback gratuito para preço**; fundamentals úteis mas throughput free baixo | Plano individual é pessoal/interno; sem redistribuição/display comercial; free aguenta watchlists pequenas. citeturn11view0turn13search3turn38search1turn15view1turn15view2 |
| urlFinnhubturn45search1 | Preço, candles, fundamentals normalizados, profile/basic financials | Free “All-In-One” | 60 req/min free; 300 req/min fundamentals; 900 req/min market data; 30 req/s hard cap | Boa, mas a descrição oficial de cobertura free é menos transparente que em Twelve Data | Boa, com disclaimer de accuracy/completeness | Baixa/média | **Boa camada opcional** | Uso estritamente pessoal; proibido redistribuir ou partilhar acesso/dados/resultados derivados sem aprovação escrita. citeturn31search0turn30search0turn28search0turn37view0 |
| urlyfinanceturn4search0 / urlYahoo Financeturn45search0 | Preços, statements e metadata de forma não oficial | Sem fee do wrapper | Sem SLA/API pública estável para este uso | Muito ampla na prática | Aceitável para exploração, **não** para dependência de produção | Muito baixa | **Não recomendada** como base principal | Wrapper não oficial; docs falam em research/educational; a própria Yahoo restringe automação fora das APIs oficiais e pode impor quotas/cessar acesso. citeturn4search0turn4search15turn46search0turn6search0 |
| urlStooqturn33search1 | Histórico de preços via CSV/site | Gratuito | Download com autorização/CAPTCHA/manual | Price-only | Útil como recurso manual | Muito baixa | **Não** para pipeline | Não é uma resposta séria para automação diária de analysis-grade data. citeturn33search0turn33search4 |

A leitura da tabela é simples: **SEC** resolve melhor o problema de fundamentals; **Twelve Data** resolve melhor o problema de preço gratuito; **Finnhub** é a melhor terceira camada; **Alpha Vantage free** e **yfinance** não são bons candidatos a provider principal para o teu pipeline. citeturn36view3turn13search3turn15view1turn28search0turn37view0turn19search0turn17view0turn4search0turn6search0

## Análise por provider

### urlSEC EDGAR / data.sec.govturn35view1

O SEC é, de longe, a fonte mais forte para fundamentals de empresas dos EUA porque o dado vem diretamente do universo de filings e XBRL do regulador. As APIs públicas expõem `companyconcept`, `companyfacts` e `frames`; o `companyfacts` devolve todos os conceitos de uma empresa numa única chamada; e as APIs XBRL são atualizadas com atraso típico inferior a um minuto após disseminação do filing. Além disso, o SEC publica arquivos bulk (`companyfacts.zip` e `submissions.zip`), o que é ótimo para pipelines diários com histórico e preservação de estado. citeturn35view1turn36view3

Do ponto de vista operacional, o SEC permite automação, mas exige fair access: a taxa máxima publicada é 10 requests/segundo e tens de declarar `User-Agent` nos headers. Isto encaixa bem num pipeline diário em GitHub Actions ou cron, desde que implementes throttling simples e fetch incremental. citeturn36view1

A limitação decisiva é que o SEC **não é um provider de preços**. Nos materiais oficiais revistos, o escopo é filings, submissions e factos XBRL em JSON; não há uma API de quotes ou séries de preço. Portanto, o SEC pode substituir ou complementar a FMP em statements, mas nunca em `price_eod`. citeturn35view0turn35view2turn36view3

Também convém manter uma atitude conservadora: o próprio SEC diz que os data sets derivados não são garantidamente exatos, não refletem toda a metadata disponível e não substituem a leitura dos filings originais. Para uma máquina de scoring/valuation isto continua a ser excelente matéria-prima; para auditoria humana final, deves manter rastreabilidade ao filing e ao accession number. citeturn36view0

**Veredito:** melhor fallback gratuito de fundamentals para empresas dos EUA; sozinho não resolve a tua app porque falta preço. citeturn36view3turn36view0

### urlAlpha Vantageturn45search2

A Alpha Vantage tem, tecnicamente, quase tudo o que te apeteceria: séries históricas, `INCOME_STATEMENT`, `BALANCE_SHEET`, `CASH_FLOW` e `SHARES_OUTSTANDING`. Além disso, documenta mapeamentos normalizados para taxonomias GAAP/IFRS e disponibiliza shares outstanding de forma explícita, o que é útil para valuation. citeturn23view0turn22view4turn22view5turn22view1

O problema está no free tier e nos termos. O suporte oficial fala em **25 requests por dia** no plano gratuito. A documentação também deixa claro que o `outputsize=full` do histórico diário é premium e que `TIME_SERIES_DAILY_ADJUSTED` é um endpoint premium. Ou seja: mesmo ignorando tudo o resto, o teu caso de uso de pipeline diário e histórico profundo fica muito condicionado no free tier. citeturn19search0turn22view2turn22view0turn20search0

O aspeto mais importante, no entanto, é jurídico: os termos publicados dizem que a licença base é para personal, non-commercial use e, logo a seguir, classificam como “commercial use” coisas como investment analysis, research, testing e monitoring. Para uma app pessoal privada isto não é o enquadramento mais confortável; eu não construiria a tua camada de fallback em cima de um texto contratual tão agressivo sem clarificação escrita. citeturn17view0turn18view1

**Veredito:** API tecnicamente interessante, mas eu **não a recomendaria** como fallback principal gratuito para o teu produto. citeturn19search0turn17view0

### urlTwelve Dataturn45search3

O Twelve Data é o melhor candidato gratuito para resolver o teu problema de **preço**. A documentação de suporte diz que os intervalos diários (`1day`, `1week`, `1month`) têm histórico completo desde a primeira data de trading para a maioria dos símbolos, e que os preços diários/semanais/mensais são ajustados para splits. Isto é exatamente o que precisas para alimentar `price_eod`, histórico preservado e cálculo de factores/valuation dependentes de preço. citeturn13search3turn38search1

O plano Basic gratuito tem **8 API credits por minuto e 800 por dia**, com **3 mercados**. A mesma página mostra que um pedido a `time_series` pesa 1 crédito, enquanto `income_statement` pesa 100 créditos por símbolo. A inferência prática é simples: o Twelve Data free é ótimo para preço, mas é apertado para statements em volume. Se fores buscar `income_statement + balance_sheet + cash_flow` para um símbolo, gastas cerca de 300 créditos; com 800/dia, isso dá para pouco mais de duas refreshes completas de fundamentals por dia. Para uma watchlist pequena pode chegar; para muitos fallbacks no mesmo dia, não. citeturn11view0turn9view1

Em termos de licenciamento, a situação é melhor do que em Alpha Vantage: os planos individuais são “strictly for personal or internal use” e **não permitem** redistribuição nem display comercial a terceiros. Para uma app pessoal privada, autenticada e só para ti, isto é compatível; para partilhar com amigos, clientes ou equipa, deixaria de o ser. citeturn15view1

Há um caveat importante no preço US realtime: o próprio Twelve Data explica que a feed de US equities incluída por defeito cobre aproximadamente **5% do volume total de trading** dos EUA e é pensada como solução compliant e cost-efficient para analytics e apps. Isso é uma nota relevante para uso execution-grade ou intraday ultra exigente, mas para um pipeline diário de análise fundamental e preço EOD continua a ser um compromisso bastante aceitável. citeturn15view2

**Veredito:** **melhor fallback gratuito para preço** no teu caso; como fallback de fundamentals, útil mas seletivo por causa dos credits. citeturn13search3turn11view0turn15view1

### urlFinnhubturn45search1

O Finnhub é um caso intermédio interessante. A página de pricing indexada publica um plano free “All-In-One”, `License: Personal Use`, e os snippets oficiais apontam para **60 API calls/minute** no free, ficando o market data a **900/min** e o fundamentals a **300/min** nas páginas especializadas. Além disso, os termos impõem um hard cap adicional de **30 API calls/second**. Em termos de cadência, é muito mais respirável do que Alpha Vantage free e, para uma watchlist pessoal, perfeitamente viável. citeturn31search0turn30search0turn37view0

O ponto mais forte do Finnhub é que a documentação indexada para `financials-reported` fala em **standardized balance sheet, income statement and cash flow** para empresas globais, com histórico de **30+ years**, sourced from original filings. Isso torna-o um bom candidato quando queres dados padronizados sem construir logo toda a camada XBRL do SEC. citeturn28search0

O lado negativo é contratual: os termos proíbem redistribuir ou partilhar acesso a dados **ou resultados derivados dos dados** sem aprovação escrita, e dizem explicitamente que os planos do site são estritamente para personal use, não podendo ser usados por business אפילו internamente sem aprovação. Para uma app só tua, isto ainda pode servir; para qualquer evolução multiutilizador, deixa de servir imediatamente. Além disso, o próprio Finnhub diz que não garante accuracy/completeness dos dados. citeturn37view0

**Veredito:** boa camada opcional/terciária para uma app privada de um único utilizador; não a escolheria antes de SEC + Twelve Data. citeturn28search0turn37view0

### urlyfinanceturn4search0 e urlYahoo Financeturn45search0

O yfinance continua a ser extremamente conveniente do ponto de vista técnico, mas os próprios docs do projeto dizem duas coisas que, para mim, encerram quase a discussão: é **não afiliado** à Yahoo e é “intended for research and educational purposes”. Isto coloca-o na categoria “ferramenta de exploração/prototipagem”, não na categoria “provider em que eu basearia valuation e signal production”. citeturn4search0turn4search15

A Yahoo Finance, enquanto serviço web, permite visualizar e descarregar histórico, dividendos e splits, e nota até que nem todos os instrumentos disponibilizam download por restrições de licenciamento. Isto confirma que há dado disponível no produto web, mas não equivale a uma API pública oficial e estável para um pipeline automático como o teu. citeturn46search0turn46search5

O fator decisivo é o enquadramento legal e operacional: os termos de API da Yahoo falam em uso com credenciais oficiais, proíbem automação fora das Yahoo APIs e reservam-se o direito de definir quotas, restringir acesso ou cessar disponibilização a qualquer momento. Juntando isso ao facto de o wrapper ser não oficial, o risco de quebra e de ambiguidade jurídica é demasiado alto para o papel de provider principal. citeturn6search0

**Veredito:** aceitável para notebooks, testes locais e sanity checks; **não recomendada** como dependência central do teu pipeline. citeturn4search0turn6search0

### urlStooqturn33search1

A única razão para mencionar o Stooq é que ele existe como fonte gratuita de histórico de preços. Mas as páginas oficiais indexadas mostram download manual/CSV com autorização/CAPTCHA. Isso pode ser útil para recuperação manual de uma série ou validação ad hoc, mas não é uma base séria para um pipeline diário automatizado. citeturn33search0turn33search4

## Viabilidade do fallback SEC

O fallback SEC é **viável** e, para empresas dos EUA, faz todo o sentido implementar antes de procurares um novo provider “all-in-one”. A forma certa de pensar nisto é: o SEC não substitui a FMP inteira; substitui sobretudo a parte de **statements/fundamentals**. E faz isso com uma qualidade de origem que mais nenhum provider gratuito consegue igualar, porque o dado vem da própria infraestrutura de filings do regulador. citeturn35view1turn36view3

Tecnicamente, eu usaria `companyfacts` e `companyconcept` para montar `statements_norm`; não usaria `frames` como fonte principal de assembly dos statements. O motivo é que `companyconcept` devolve arrays separados por unidade de medida, enquanto `frames` agrega factos numa malha calendárica aproximada para dados anuais, trimestrais e instantâneos, e o próprio SEC avisa que os utilizadores devem ter cuidado com diferentes datas de início/fim de período contidas nesses frames. Para benchmarking ou factor snapshots, `frames` é útil; para construir demonstrações consistentes por empresa, `companyfacts/companyconcept` é mais sólido. citeturn36view4turn36view5

Para os teus campos canónicos, a cobertura SEC é suficientemente boa **na maioria das empresas americanas operacionais** se tiveres uma camada de mapeamento. Um bom ponto de partida prático é observar os mapeamentos GAAP públicos documentados pela Alpha Vantage: `totalRevenue -> Revenues`, `grossProfit -> GrossProfit`, `operatingIncome -> OperatingIncomeLoss`, `netIncome -> NetIncomeLoss`, `operatingCashflow -> NetCashProvidedByUsedInOperatingActivities`, `capitalExpenditures -> PaymentsToAcquireProductiveAssets`, `cashAndCashEquivalentsAtCarryingValue`, `totalAssets -> Assets`, `totalLiabilities -> Liabilities`, `totalShareholderEquity -> StockholdersEquity`, `currentDebt/longTermDebt/debtLongtermAndShorttermCombinedAmount` para dívida. Em cima disso, `FCF` é derivável como `CFO - capex`. citeturn41view1turn39view3turn39view2turn39view0turn39view5turn39view6turn39view7turn40view2turn40view3

Os dois pontos mais delicados são precisamente aqueles que costumam bloquear valuation: **EBIT/EBITDA** e **shares outstanding**. No mapeamento público acima, `ebit` e `ebitda` aparecem como **“Not a GAAP Tag”**, o que é um forte sinal de que, em SEC raw data, os deves tratar como métricas derivadas e não como factos primários confiáveis em todas as empresas. E `commonStockSharesOutstanding` é explicitamente descrito como **“Best estimate”**, podendo cair para quarterly weighted average basic shares quando a empresa não reporta um valor de fim de período. Portanto: statements core, sim; FCF, sim por derivação; shares period-end/diluted clean, nem sempre. citeturn39view9turn39view10turn39view1

Os principais desafios de normalizar SEC XBRL são estes:

- **Taxonomias e extensões custom**: o SEC explica que os factos XBRL têm de estar associados a taxonomias US-GAAP ou IFRS, mas as empresas também podem estender taxonomias standard com conceitos próprios; isso obriga a uma camada de aliasing/prioridades e a exceções por setor/emissor. citeturn36view5
- **Unidades e escalas**: `companyconcept` devolve factos por unidade; tens de escolher unidade, escala e sinal corretos antes de popular `statements_norm`. citeturn36view4
- **Períodos**: valores instantâneos, trimestrais e anuais coexistem e nem sempre alinham com anos civis; tens de normalizar pelo `fy/fp/form/filed/end/frame` e não apenas pela data do ficheiro. citeturn36view5
- **Shares outstanding**: period-end shares clean é um dos campos menos uniformes; muitas vezes vais preferir uma regra de fallback explícita ou uma segunda fonte para validar. citeturn39view1
- **Preço inexistente**: SEC resolve fundamentals, não preço. Portanto nunca será um fallback isolado para a tua app. citeturn35view0turn35view2turn36view3

A resposta curta à tua pergunta central é, portanto: **sim, o SEC companyfacts pode preencher `statements_norm` de forma suficientemente robusta para muitas empresas dos EUA**, sobretudo para os campos usados num DCF/quality model clássico; **não**, não é uma substituição universal de FMP sem trabalho de normalização, derivação e um fallback separado para preço e, em alguns casos, para shares outstanding. citeturn36view3turn39view2turn39view3turn39view5turn39view6turn39view7turn39view1

## Arquitetura de fallback recomendada

A arquitetura que eu recomendaria para o teu produto é esta.

### Provider primário

Mantém a FMP como **provider primário** porque já tens integração feita e, para os tickers suportados, o pipeline já corre end-to-end de forma estável no teu stack atual. A mudança aqui não é “trocar de provider”; é passar de single-provider frágil para orchestration por prioridade de fonte. 

### Fallback de fundamentals

Quando a FMP falhar em statements/fundamentals para uma empresa dos EUA, o primeiro fallback deve ser o urlSEC EDGAR / data.sec.govturn35view1. No teu contexto, isto faz mais sentido do que saltar logo para outro vendor porque o SEC é gratuito, oficial, automatizável e atualizado praticamente em tempo real após filing. Para backfill e estabilidade, aproveitaria também os arquivos bulk `companyfacts.zip` e `submissions.zip`. citeturn36view3turn36view1

Praticamente, eu criaria uma camada `sec_xbrl_adapter` com estas responsabilidades:

- resolver `CIK` e metadados do emissor;
- extrair factos de `companyfacts/companyconcept`;
- escolher a melhor observação por conceito com base em `fy/fp/form/filed/end`;
- mapear para o teu esquema canónico (`statements_norm`);
- derivar `FCF`, `EBIT` e `EBITDA` quando necessário;
- persistir **proveniência por campo** (`source_provider`, `source_endpoint`, `source_concept`, `accession_number`, `filed_date`);
- emitir um `data_quality_flag` quando um campo vier de derivação ou fallback fraco.  

Isto reduz muito o risco de “inventar” dados e permite explicar na UI o que veio do regulador e o que veio de vendor. citeturn36view3turn36view4turn36view5turn39view1

### Fallback de preço

Para preço, o melhor fallback free é o urlTwelve Dataturn45search3. O racional é simples: histórico diário profundo, preço ajustado para splits em daily/weekly/monthly, integração simples e termos compatíveis com uso pessoal/interno. O SEC não resolve preço; Alpha free não resolve histórico/pricing suficiente; yfinance não é provider oficial. citeturn13search3turn38search1turn15view1turn22view2turn4search0turn6search0

Eu usaria o Twelve Data **prioritariamente para `price_eod` e `latest_price`** e só **seletivamente** para fundamentals em free, porque o custo em credits por statement é alto. Em termos práticos, isso significa:

- `FMP price` falha → tentar `Twelve time_series`;
- `FMP statements` falham → tentar `SEC`;
- se `SEC` preencher 90–95% do teu canónico mas faltar um campo crítico como share count de fim de período, então tentar uma **camada secundária opcional** com Twelve Data ou Finnhub apenas para esse campo, e marcar isso explicitamente na proveniência. citeturn11view0turn13search3turn15view1turn28search0turn37view0

### Orquestração e regras de aceitação/rejeição

Eu mudaria a lógica de aprovação de empresas na watchlist. Não faz sentido aprovar silenciosamente uma empresa que vai inevitavelmente acabar num dashboard com `missing_inputs` crónico, a menos que o objetivo seja explicitamente “tracking only”.

A regra que eu recomendaria é esta:

- **Aprovar para análise completa** se existir pelo menos um caminho válido para:
  - fundamentals suficientes (`FMP` **ou** `SEC`);
  - preço diário (`FMP` **ou** `Twelve Data`);
  - share-count path aceitável (`FMP` **ou** SEC com cobertura suficiente **ou** fallback vendor adicional).
- **Rejeitar como unsupported** se não houver caminho mínimo para valuation-grade data.
- **Tracking-only** apenas por opt-in explícito do utilizador.  

Para o teu caso, isto significa que empresas americanas com `CIK` e filings estruturados devem deixar de ser rejeitadas só porque a FMP devolve 402; mas empresas sem SEC structured data e sem fallback de preço/compliance não deviam entrar automaticamente na área de análise. citeturn35view1turn36view3turn13search3turn15view1turn46search0

### Camada opcional de validação

A urlFinnhubturn45search1 ficaria como camada opcional de verificação ou desbloqueio de edge cases, não como primeiro fallback. Isto é particularmente útil se quiseres comparar um subconjunto dos campos derivados do SEC com um vendor que já te devolve statements padronizados. Mas eu só faria isto depois de o SEC adapter e o fallback de preço estarem sólidos. citeturn28search0turn37view0

## Riscos, termos e prioridade de implementação

O maior risco técnico de uma arquitetura multi-provider não é a integração; é a **mistura silenciosa de dados inconsistentes**. O remédio é simples: persistir proveniência por campo, distinguir factos primários de métricas derivadas e calcular `valuation` apenas quando o conjunto mínimo de campos estiver completo e coerente no mesmo período fiscal. Sem isso, mudas o problema de “missing inputs” para o problema mais perigoso de “inputs misturados”. 

O maior risco legal é este:

- com urlTwelve Dataturn45search3 e urlFinnhubturn45search1, uma **app pessoal privada** parece compatível, mas redistribuição ou multiutilizador exigem rever licenças; citeturn15view1turn37view0
- com urlAlpha Vantageturn45search2, eu trataria a compatibilidade como fraca/ambígua para o teu caso; citeturn17view0turn18view1
- com urlyfinanceturn4search0 / urlYahoo Financeturn45search0, o risco jurídico e operacional é alto demais para dependência central. citeturn4search0turn6search0

A prioridade de implementação que eu seguiria é esta:

**Melhoria de diagnóstico e proveniência.**  
Antes de qualquer novo provider, acrescenta preflight de cobertura no add-request e guarda provenance por campo. Isto evita aprovações “mortas à chegada” e prepara a UI para explicar porque uma empresa foi aceite, rejeitada ou degradada.

**Fallback SEC para fundamentals.**  
Este é o passo com mais impacto estrutural. Resolve o teu problema principal para empresas americanas, melhora auditabilidade e reduz dependência de vendor gating por ticker/endpoint. Usa `companyfacts/companyconcept` no dia a dia e bulk ZIPs para backfill. citeturn36view3turn36view4turn36view5

**Fallback Twelve Data para preço.**  
Isto fecha a principal lacuna que o SEC não resolve. Implementa `latest_price` + `price_eod` + histórico diário, preferencialmente com cache incremental. citeturn13search3turn38search1turn15view1

**Orquestração de provider e rejeição automática de unsupported companies.**  
Quando os dois fallbacks estiverem vivos, altera a lógica de aprovação: aprovar empresas apenas se houver caminho real para análise; caso contrário, rejeitar ou forçar `tracking_only` explícito.

**Camada opcional Finnhub.**  
Só depois disto eu avaliaria Finnhub como verificação complementar ou preenchimento de um pequeno conjunto de campos difíceis. citeturn28search0turn37view0

A minha recomendação final é objetiva: **implementa primeiro o fallback SEC para fundamentals e o fallback Twelve Data para preço**. É a combinação gratuita mais alinhada com os teus objetivos de fiabilidade, valuation e uso privado. **Não avançaria primeiro para uma fase puramente de status de disponibilidade**, e **não escolheria yfinance ou Alpha Vantage free** como solução central para este problema. citeturn36view3turn13search3turn15view1turn19search0turn17view0turn4search0turn6search0
