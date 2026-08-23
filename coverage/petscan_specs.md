# Retiring the PETScan category queries

Measured 2026-08-23 by `scripts/spec_report.py`. 284 of the 594 specs in `wd_categories.yml` carry a synthetic
`position:` block; this is what it would take to **delete each query**.

The crawler applies a spec's `topic:` to its members independently of the
`position:` block, so deleting a whole spec removes the PEP topic, the
country and the synthetic occupancy together. The replacement therefore has
to be `wd_peps` emitting those people from their own statements — which is a
stronger condition than every member holding the target, and the reason this
report audits the *target item* as well as the members.

| disposition | specs | people in the gap |
|---|---:|---:|
| `retirable` | 22 | 0 |
| `enrich` | 72 | 1970 |
| `fix-item` | 4 | 7 |
| `os-policy` | 110 | 2292 |
| `bucket` | 24 | 0 |
| `unresolved` | 28 | 2405 |
| `broken-query` | 24 | 0 |

**Only the first two rows are reachable by enriching Wikidata.** `os-policy`
is the class the workaround genuinely exists for, and it does not shrink no
matter how many P39 statements this workbench writes.

## `retirable` (22 specs)

The target is a position `wd_peps` emits, and every human member already holds it. **Delete these specs from `wd_categories.yml`.**

| category | lang | members | holds | gap | target | why |
|---|---|---:|---:|---:|---|---|
| `21st-century_members_of_the_House_of_Commons_of_Canada` | en | 1179 | 1179 | 0 | Q15964890 member of the House of Commons of Canada |  |
| `Депутаты Государственной думы Российской Федерации VII созыва` | ru | 498 | 498 | 0 | Q17276321 member of the State Duma |  |
| `Országgyűlési_képviselők_(2022–2026)` | hu | 209 | 209 | 0 | Q17590876 member of the National Assembly of Hungary |  |
| `Members_of_the_National_Assembly_of_Hungary_(2022–2026)` | en | 172 | 172 | 0 | Q17590876 member of the National Assembly of Hungary |  |
| `Australian_MPs_2022–2025` | en | 155 | 155 | 0 | Q18912794 member of the Australian House of Representatives |  |
| `Presidents_of_the_United_States` | en | 45 | 45 | 0 | Q11696 President of the United States |  |
| `Chief_justices_of_the_United_States` | en | 17 | 17 | 0 | Q11147 Chief Justice of the United States |  |
| `Депутаты Думы Ханты-Мансийского автономного округа — Югры` | ru | 13 | 13 | 0 | Q124755389 Deputy of the Duma of Khanty-Mansi Autonomous Okrug — Yugra |  |
| `Председатели Правительства РФ` | ru | 12 | 12 | 0 | Q842386 Prime Minister of Russia |  |
| `Defence_ministers_of_Belarus` | en | 7 | 7 | 0 | Q44035369 Defence Minister of Belarus |  |
| `Justice_ministers_of_Belarus` | en | 7 | 7 | 0 | Q106510814 Minister of Justice of the Republic of Belarus |  |
| `Secretaries-general_of_the_Gulf_Cooperation_Council` | en | 5 | 5 | 0 | Q104127429 Secretary-General of the Gulf Cooperation Council |  |
| `Health_ministers_of_Belarus` | en | 4 | 4 | 0 | Q89775465 Minister of Health of the Republic of Belarus |  |
| `Industry_ministers_of_Belarus` | en | 4 | 4 | 0 | Q106508605 Minister of Industry of the Republic of Belarus |  |
| `Lietuvos_prezidentai` | lt | 4 | 4 | 0 | Q878222 President of the Republic of Lithuania |  |
| `Председатели Совета Федерации России` | ru | 4 | 4 | 0 | Q4376672 Chairman of the Federation Council of Russia |  |
| `Члены Совета Федерации России от Камчатского края` | ru | 4 | 4 | 0 | Q4516946 member of the Federation Council of Russia |  |
| `Finance_ministers_of_Belarus` | en | 3 | 3 | 0 | Q106510813 Minister of Finance of the Republic of Belarus |  |
| `Information_ministers_of_Belarus` | en | 3 | 3 | 0 | Q106399613 Minister of Information of the Republic of Belarus |  |
| `Transport_ministers_of_Belarus` | en | 2 | 2 | 0 | Q60676745 Minister of Transport and Communications of the Republic of Belarus |  |
| `Members_of_the_Bundestag` | en | 1 | 1 | 0 | Q1939555 member of the German Bundestag |  |
| `Senadores_de_Colombia` | es | 0 | 0 | 0 | Q19254253 member of the Senate of Colombia |  |

## `enrich` (72 specs)

The target is emittable and members are missing the statement. This is the enrichment loop's queue; `gap` is the upper bound before the cohort relevance gate.

| category | lang | members | holds | gap | target | why |
|---|---|---:|---:|---:|---|---|
| `Members_of_the_Australian_Senate` | en | 657 | 656 | 1 | Q6814428 member of the Australian Senate |  |
| `Members_of_the_Senate_(Netherlands)` | en | 310 | 309 | 1 | Q19305384 member of the Senate of the Netherlands |  |
| `Lietuvos_ministrai_pirmininkai` | lt | 19 | 18 | 1 | Q845439 Prime Minister of Lithuania |  |
| `Secretaries_general_of_NATO` | en | 17 | 16 | 1 | Q167662 Secretary General of NATO |  |
| `Члены Совета Федерации России от Рязанской области` | ru | 14 | 13 | 1 | Q4516946 member of the Federation Council of Russia |  |
| `Secretaries-general_of_the_United_Nations` | en | 11 | 10 | 1 | Q81066 United Nations Secretary-General |  |
| `Члены Совета Федерации России от Приморского края` | ru | 11 | 10 | 1 | Q4516946 member of the Federation Council of Russia |  |
| `Foreign_ministers_of_Belarus` | en | 10 | 9 | 1 | Q2045068 Minister of Foreign Affairs of Belarus |  |
| `Члены Совета Федерации России от Хабаровского края` | ru | 10 | 9 | 1 | Q4516946 member of the Federation Council of Russia |  |
| `Lietuvos_generaliniai_prokurorai` | lt | 8 | 7 | 1 | Q132068652 Prosecutor General of Lithuania |  |
| `Interior_ministers_of_Belarus` | en | 6 | 5 | 1 | Q100699741 Minister of Internal Affairs of the Republic of Belarus |  |
| `Члены Совета Федерации России от Республики Крым` | ru | 4 | 3 | 1 | Q4516946 member of the Federation Council of Russia |  |
| `Мэры Москвы` | ru | 4 | 3 | 1 | Q1837906 mayor of Moscow |  |
| `Presidents_of_Nicaragua` | en | 68 | 66 | 2 | Q852448 President of Nicaragua |  |
| `Presidentes_de_Nicaragua` | es | 67 | 65 | 2 | Q852448 President of Nicaragua |  |
| `Presidents_of_Venezuela` | en | 52 | 50 | 2 | Q11942698 President of Venezuela |  |
| `Presidentes_de_Guatemala` | es | 50 | 48 | 2 | Q6085537 president of Guatemala |  |
| `Presidentes_de_Venezuela` | es | 31 | 29 | 2 | Q11942698 President of Venezuela |  |
| `Члены Совета Федерации России от Волгоградской области` | ru | 14 | 12 | 2 | Q4516946 member of the Federation Council of Russia |  |
| `Mayors_of_Guatemala_City` | en | 9 | 7 | 2 | Q116790781 Mayor of Guatemala |  |
| `Communications_ministers_of_Belarus` | en | 3 | 1 | 2 | Q28598480 Minister of Communications and Informatization of the Republic of Belarus |  |
| `Депутаты Государственной думы Российской Федерации от одномандатных округов` | ru | 869 | 866 | 3 | Q17276321 member of the State Duma |  |
| `Diputados_de_la_LXV_Legislatura_de_México` | es | 338 | 335 | 3 | Q18534310 Member of the Chamber of Deputies of Mexico |  |
| `Diputados_de_la_LXIV_Legislatura_de_México` | es | 288 | 285 | 3 | Q18534310 Member of the Chamber of Deputies of Mexico |  |
| `Presidents_of_the_Senate_of_Spain` | en | 39 | 36 | 3 | Q1335465 President of the Spanish Senate |  |
| `Members_of_the_Senate_of_Venezuela` | en | 33 | 30 | 3 | Q20081434 senator of Venezuela |  |
| `Seimo_nariai` | lt | 668 | 664 | 4 | Q18507240 Member of the Seimas |  |
| `Members_of_the_House_of_Representatives_(Netherlands)` | en | 423 | 419 | 4 | Q18887908 member of the House of Representatives of the Netherlands |  |
| `13._Saeimas_deputāti` | lv | 126 | 122 | 4 | Q21191589 deputy of Saeima |  |
| `Presidents_of_Guatemala` | en | 25 | 21 | 4 | Q6085537 president of Guatemala |  |
| `Lietuvos_banko_vadovai` | lt | 10 | 5 | 5 | Q109496871 Governor of the Bank of Lithuania |  |
| `21st-century_members_of_the_Senate_of_Canada` | en | 299 | 293 | 6 | Q18524027 member of the Senate of Canada |  |
| `Prime_ministers_of_Belarus` | en | 17 | 11 | 6 | Q12379704 Prime Minister of Belarus |  |
| `Presidents_of_Colombia` | en | 38 | 31 | 7 | Q853475 President of Colombia |  |
| `Members_of_the_National_Assembly_(Nicaragua)` | en | 28 | 19 | 9 | Q18616113 Member of the National Assembly of Nicaragua |  |
| `Members_of_the_Hellenic_Parliament` | en | 20 | 11 | 9 | Q18915989 member of the Hellenic Parliament |  |
| `Lietuvos_kariuomenės_vadai` | lt | 16 | 7 | 9 | Q55607326 Chief of Defence of Lithuania |  |
| `Депутаты Государственной думы Российской Федерации VIII созыва` | ru | 473 | 463 | 10 | Q17276321 member of the State Duma |  |
| `Первые заместители председателя Правительства Российской Федерации` | ru | 28 | 18 | 10 | Q1965788 First Deputy Chairman of the Government of the Russian Federation |  |
| `Members_of_the_Congress_of_Guatemala` | en | 58 | 47 | 11 | Q18277108 Member of the Congress of Guatemala |  |
| `Руководители Аппарата Правительства Российской Федерации` | ru | 18 | 7 | 11 | Q107883642 Chief of the Government Staff |  |
| `Mayors_of_Managua` | en | 11 | 0 | 11 | Q104881755 Mayor of Managua |  |
| `Mayors_of_Bogotá` | en | 28 | 16 | 12 | Q21994938 Mayor of Bogota |  |
| `Заместители председателя Правительства Российской Федерации` | ru | 80 | 67 | 13 | Q14805701 Deputy Chairman of the Government of the Russian Federation |  |
| `Diputados_de_Guatemala` | es | 45 | 32 | 13 | Q18277108 Member of the Congress of Guatemala |  |
| `Депутаты Парламента Чеченской Республики` | ru | 13 | 0 | 13 | Q133268407 Member of the Parliament of the Chechen Republic |  |
| `Deputy_prime_ministers_of_Belarus` | en | 30 | 12 | 18 | Q18690228 Deputy Prime Minister of the Republic of Belarus |  |
| `Депутаты Государственного Совета Удмуртской Республики` | ru | 20 | 2 | 18 | Q108610448 Deputy of the State Council of the Udmurt Republic |  |
| `Members_of_the_National_Congress_(Ecuador)` | en | 76 | 49 | 27 | Q22230757 National Congress Deputy |  |
| `Senadores_de_las_LXIV_y_LXV_Legislaturas_de_México` | es | 168 | 140 | 28 | Q19971999 member of the Senate of Mexico |  |
| `Депутаты Московской областной думы` | ru | 36 | 0 | 36 | Q110805962 Member of Moscow Oblast Duma |  |
| `Presidents_of_Ecuador` | en | 82 | 43 | 39 | Q732562 President of Ecuador |  |
| `Депутаты Московской городской думы` | ru | 53 | 14 | 39 | Q96324124 member of the Moscow City Duma |  |
| `Presidentes_de_Ecuador` | es | 82 | 38 | 44 | Q732562 President of Ecuador |  |
| `Presidentes_de_Colombia` | es | 106 | 61 | 45 | Q853475 President of Colombia |  |
| `Депутаты Народного собрания Дагестана` | ru | 48 | 1 | 47 | Q115242140 member of the People's Assembly of the Republic of Dagestan |  |
| `Члены Совета Федерации России (с 2000)` | ru | 779 | 730 | 49 | Q4516946 member of the Federation Council of Russia |  |
| `Members_of_the_National_Council_(Slovakia)_2023–2027` | en | 71 | 21 | 50 | Q19967563 Member of the National Council of the Slovak Republic |  |
| `Members_of_the_Congress_of_Deputies_(Spain)` | en | 99 | 43 | 56 | Q18171345 Member of the Congress of Deputies |  |
| `Poslanci_NR_SR_(2020_–_2023)` | sk | 94 | 31 | 63 | Q19967563 Member of the National Council of the Slovak Republic |  |
| `Members_of_the_Polish_Sejm_2023–2027` | en | 344 | 280 | 64 | Q19269361 member of the Sejm |  |
| `Депутаты Совета Федерации России (1993—1995)` | ru | 177 | 111 | 66 | Q4516946 member of the Federation Council of Russia |  |
| `Members_of_the_Senate_of_Spain` | en | 193 | 124 | 69 | Q19323171 member of the Senate of Spain |  |
| `Члены Совета Федерации России (1996—2000)` | ru | 275 | 198 | 77 | Q4516946 member of the Federation Council of Russia |  |
| `Members_of_the_Supreme_People's_Assembly` | en | 147 | 66 | 81 | Q21328639 member of the Supreme People's Assembly |  |
| `Senadores_de_las_LXVI_y_LXVII_Legislaturas_de_México` | es | 123 | 42 | 81 | Q19971999 member of the Senate of Mexico |  |
| `14._Saeimas_deputāti` | lv | 129 | 45 | 84 | Q21191589 deputy of Saeima |  |
| `Senatorowie_XI_kadencji_Senatu_Rzeczypospolitej_Polskiej` | pl | 102 | 17 | 85 | Q81747225 Member of the Senate of the Republic of Poland |  |
| `Members_of_the_National_Assembly_(Ecuador)` | en | 104 | 16 | 88 | Q21295982 Member of the National Assembly of Ecuador |  |
| `Prime_ministers_of_Spain` | en | 116 | 15 | 101 | Q844587 Prime Minister of Spain |  |
| `Posłowie_na_Sejm_Rzeczypospolitej_Polskiej_X_kadencji` | pl | 497 | 391 | 106 | Q19269361 member of the Sejm |  |
| `Asambleístas_y_diputados_de_Ecuador` | es | 299 | 5 | 294 | Q21295982 Member of the National Assembly of Ecuador |  |

## `fix-item` (4 specs)

The target carries a Wikidata modelling defect, so `wd_peps` skips it however good the P39s are. Fix the item first (`recipes/position_items.md`), then the spec becomes `enrich`.

| category | lang | members | holds | gap | target | why |
|---|---|---:|---:|---:|---|---|
| `LR_Seimo_pirmininkai` | lt | 16 | 16 | 0 | Q12663218 Speaker of the Seimas | surgical, also_a_list_article |
| `Crown_princes_of_Saudi_Arabia` | en | 12 | 12 | 0 | Q12251224 Crown Prince of Saudi Arabia | surgical, also_a_list_article |
| `Руководители Администрации президента России` | ru | 12 | 11 | 1 | Q4488944 Kremlin Chief of Staff | untyped, untyped |
| `Presidents_of_the_National_Assembly_(Ecuador)` | en | 10 | 4 | 6 | Q6085548 President of the National Assembly of Ecuador | surgical, also_a_list_article |

## `os-policy` (110 specs)

**Keep these specs.** The target is well-modelled Wikidata that `wd_peps` still declines: `pep_default_off` means no PEP-conferring parent in `zavod`'s `SUB_TYPES`, `excluded_type` means the type closure reaches an award or title of honour with nothing to rescue it. Enriching Wikidata cannot retire these — they need a decision in the OpenSanctions position review, or a `SUB_TYPES` change upstream. This is the class the PETScan workaround genuinely exists for.

| category | lang | members | holds | gap | target | why |
|---|---|---:|---:|---:|---|---|
| `21st-century_members_of_the_Nova_Scotia_House_of_Assembly` | en | 197 | 197 | 0 | Q18239264 member of the Nova Scotia House of Assembly | upstream |
| `NATO_Supreme_Allied_Commanders` | en | 19 | 19 | 0 | Q1640949 Supreme Allied Commander Europe | review |
| `Presidents_of_the_World_Bank_Group` | en | 14 | 14 | 0 | Q4166474 President of the World Bank Group | review |
| `Presidents_of_the_European_Commission` | en | 14 | 14 | 0 | Q8882 President of the European Commission | review |
| `Presidents_of_FIFA` | en | 11 | 11 | 0 | Q22955080 president of FIFA | review |
| `Депутаты Курской областной думы` | ru | 10 | 10 | 0 | Q133268394 Member of the Kursk Oblast Duma | upstream |
| `Presidents_of_the_International_Criminal_Court` | en | 6 | 6 | 0 | Q7241113 President of the International Criminal Court | review |
| `Председатели Верховного суда Российской Федерации` | ru | 3 | 3 | 0 | Q4431732 Chief Justice of the Russian Federation | upstream |
| `Vicepresidencia_de_Colombia` | es | 0 | 0 | 0 | Q17104133 Vice President of Colombia | upstream |
| `Депутаты Законодательного собрания Кировской области` | ru | 0 | 0 | 0 | Q133268371 member of the Legislative Assembly of Kirov Region | upstream |
| `Secretaries_general_of_OPEC` | en | 16 | 15 | 1 | Q6596647 Secretary General of OPEC | review |
| `Presidents_of_the_International_Olympic_Committee` | en | 11 | 10 | 1 | Q7241513 president of the International Olympic Committee | review |
| `Presidents_of_Interpol` | en | 9 | 8 | 1 | Q19698214 President of Interpol | review |
| `Chairpersons_of_the_African_Union_Commission` | en | 6 | 5 | 1 | Q2571270 Chairperson of the African Union Commission | review |
| `Vicepresidentes_de_Guatemala` | es | 20 | 18 | 2 | Q5340773 Vice President of Guatemala | upstream |
| `Managing_directors_of_the_International_Monetary_Fund` | en | 14 | 12 | 2 | Q20054152 Managing Director of the International Monetary Fund | review |
| `Secretaries_general_of_the_Arab_League` | en | 9 | 7 | 2 | Q12180685 Secretary General of the Arab League | review |
| `Депутаты Законодательного собрания Еврейской автономной области` | ru | 2 | 0 | 2 | Q133268367 Member of the Legislative Assembly of the Jewish Autonomous Oblast | upstream |
| `Депутаты Народного собрания Ингушетии` | ru | 2 | 0 | 2 | Q133268422 Member of the People's Assembly of the Republic of Ingushetia | upstream |
| `Secretaries_general_of_the_Organization_of_American_States` | en | 12 | 9 | 3 | Q6123153 General Secretariat of the Organization of American States | review |
| `Presidents_of_the_Inter-American_Development_Bank` | en | 6 | 3 | 3 | Q58281251 President of the Inter-American Development Bank | review |
| `21st-century_members_of_the_National_Assembly_of_Quebec` | en | 500 | 496 | 4 | Q3305338 Member of the National Assembly of Quebec | upstream |
| `Депутаты Государственного собрания Башкортостана` | ru | 4 | 0 | 4 | Q133268352 member of the State Assembly of Bashkortostan | upstream |
| `Депутаты Новгородской областной думы` | ru | 4 | 0 | 4 | Q133268402 Member of the Novgorod Oblast Duma | upstream |
| `Депутаты Думы Чукотского автономного округа` | ru | 4 | 0 | 4 | Q133268427 Member of the Duma of Chukotka Autonomous Okrug | upstream |
| `Депутаты Законодательного собрания Камчатского края` | ru | 5 | 0 | 5 | Q133268373 Member of the Legislative Assembly of Kamchatka Krai | upstream |
| `Депутаты Магаданской областной думы` | ru | 5 | 0 | 5 | Q133268396 member of the Magadan Oblast Duma | upstream |
| `Депутаты Законодательного собрания Ямало-Ненецкого автономного округа` | ru | 5 | 0 | 5 | Q133268431 Member of the Legislative Assembly of the Yamalo-Nenets Autonomous Okrug | upstream |
| `Diputados_de_Venezuela` | es | 8 | 2 | 6 | Q20011182 member of the National Assembly of Venezuela | upstream |
| `Депутаты Государственного собрания Республики Алтай` | ru | 6 | 0 | 6 | Q133268350 member of the State Assembly of the Altai Republic | upstream |
| `International_Criminal_Court_prosecutors` | en | 10 | 3 | 7 | Q7250572 Prosecutor of the International Criminal Court | review |
| `Депутаты Народного Хурала (Парламента) Республики Калмыкия` | ru | 8 | 1 | 7 | Q133268400 member of the People's Khural of Kalmykia | upstream |
| `Депутаты Законодательного собрания Севастополя` | ru | 7 | 0 | 7 | Q133268430 Member of the Legislative Assembly of Sevastopol | upstream |
| `Депутаты Парламента Кабардино-Балкарии` | ru | 7 | 0 | 7 | Q133268405 member of the Parliament of the Kabardino-Balkar Republic | upstream |
| `Депутаты Законодательного собрания Калужской области` | ru | 7 | 0 | 7 | Q133268372 Member of the Regional parliament of Kaluga | upstream |
| `Депутаты Липецкого областного Совета депутатов` | ru | 7 | 0 | 7 | Q133268395 Member of the Lipetsk Oblast Council of Deputies | upstream |
| `Депутаты Орловского областного Совета народных депутатов` | ru | 7 | 0 | 7 | Q133268404 member of the Oryol Oblast Council of People's Deputies | upstream |
| `International_Criminal_Court_judges` | en | 55 | 47 | 8 | Q965043 Judge of the International Criminal Court | review |
| `Депутаты Законодательного собрания Оренбургской области` | ru | 9 | 1 | 8 | Q111242479 Member of the Legislative Assembly of Orenburg Oblast | upstream |
| `Депутаты Архангельского областного собрания депутатов` | ru | 8 | 0 | 8 | Q133268342 member of the Arkhangelsk Oblast Assembly of Deputies | upstream |
| `Депутаты Думы Астраханской области` | ru | 8 | 0 | 8 | Q133268349 Member of the Duma of the Astrakhan Region | upstream |
| `Депутаты Тамбовской областной думы` | ru | 8 | 0 | 8 | Q133268432 Member of the Tambov Oblast Duma | upstream |
| `Депутаты Тульской областной думы` | ru | 8 | 0 | 8 | Q133268418 Member of the Tula Oblast Duma | upstream |
| `Депутаты Верховного Совета Республики Хакасия` | ru | 8 | 0 | 8 | Q133268344 member of the Supreme Council of Khakassia | upstream |
| `Депутаты Собрания депутатов Ненецкого автономного округа` | ru | 9 | 0 | 9 | Q133268415 Member of the Assembly of Deputies of the Nenets Autonomous Okrug | upstream |
| `Депутаты Законодательного собрания Ульяновской области` | ru | 9 | 0 | 9 | Q133268389 Member of the Legislative Assembly of Ulyanovsk Oblast | upstream |
| `Депутаты Государственного Собрания Республики Мордовия` | ru | 10 | 0 | 10 | Q133268353 Member of the State Assembly of the Republic of Mordovia | upstream |
| `Депутаты Законодательного собрания Тверской области` | ru | 10 | 0 | 10 | Q133268388 Member of the Legislative Assembly of Tver Oblast | upstream |
| `Депутаты Сахалинской областной думы` | ru | 11 | 0 | 11 | Q133268413 Member of the Sakhalin Oblast Duma | upstream |
| `Vice_presidents_of_Guatemala` | en | 31 | 19 | 12 | Q5340773 Vice President of Guatemala | upstream |
| `Депутаты Народного Собрания (Парламента) Карачаево-Черкесии` | ru | 12 | 0 | 12 | Q133268399 Member of the People's Assembly of the Karachay-Cherkess Republic | upstream |
| `Депутаты Совета народных депутатов Кемеровской области` | ru | 12 | 0 | 12 | Q133268417 Member of the Legislative Assembly of Kemerovo Oblast | upstream |
| `Депутаты Законодательного собрания Омской области` | ru | 12 | 0 | 12 | Q133268379 Member of the Legislative Assembly of Omsk Oblast | upstream |
| `Members_of_the_National_Assembly_(Venezuela)` | en | 109 | 96 | 13 | Q20011182 member of the National Assembly of Venezuela | upstream |
| `Депутаты Ярославской областной думы` | ru | 14 | 1 | 13 | Q133268420 Member of the Yaroslavl Oblast Duma | upstream |
| `Депутаты Алтайского краевого законодательного собрания` | ru | 13 | 0 | 13 | Q133268339 Member of the Altai Krai Legislative Assembly | upstream |
| `Депутаты Государственного собрания Республики Марий Эл` | ru | 13 | 0 | 13 | Q133268424 Member of the State Assembly of the Mari El Republic | upstream |
| `Депутаты Псковского областного Собрания депутатов` | ru | 13 | 0 | 13 | Q133268408 Member of the Pskov Oblast Assembly of Deputies | upstream |
| `Депутаты Законодательной думы Хабаровского края` | ru | 13 | 0 | 13 | Q133268361 Member of the Legislative Duma of Khabarovsk Krai | upstream |
| `Vice_presidents_of_Venezuela` | en | 25 | 11 | 14 | Q3556895 Vice President of Venezuela | upstream |
| `Депутаты Государственного Совета Республики Коми` | ru | 15 | 1 | 14 | Q111236573 Member of the State Council of the Komi Republic | upstream |
| `Депутаты Законодательного собрания Иркутской области` | ru | 14 | 0 | 14 | Q133268426 Member of the Irkutsk Legislative Assembly | upstream |
| `Депутаты Законодательного собрания Новосибирской области` | ru | 14 | 0 | 14 | Q133268380 Member of the Legislative Assembly of Novosibirsk Oblast | upstream |
| `Vice_presidents_of_Nicaragua` | en | 24 | 9 | 15 | Q3649507 Vice President of Nicaragua | upstream |
| `Депутаты Государственного совета Адыгеи` | ru | 15 | 0 | 15 | Q133268354 member of the State Council of the Republic of Adygea | upstream |
| `Депутаты Законодательного собрания Амурской области` | ru | 15 | 0 | 15 | Q133268365 Member of the Legislative Assembly of Amur Oblast | upstream |
| `Депутаты Калининградской областной думы` | ru | 15 | 0 | 15 | Q133268391 Member of the Legislative Assembly of Kaliningrad Oblast | upstream |
| `Депутаты Законодательного собрания Владимирской области` | ru | 16 | 0 | 16 | Q133268370 Member of the Legislative Assembly of Vladimir Oblast | upstream |
| `Депутаты Законодательного собрания Вологодской области` | ru | 16 | 0 | 16 | Q133268362 member of the Legislative Assembly of Vologda Oblast | upstream |
| `Депутаты Законодательного собрания Республики Карелия` | ru | 16 | 0 | 16 | Q133268366 Member of the Legislative Assembly of the Republic of Karelia | upstream |
| `Депутаты Законодательного собрания Приморского края` | ru | 16 | 0 | 16 | Q133268382 Member of the Legislative Assembly of Primorsky Krai | upstream |
| `Депутаты Парламента Республики Северная Осетия — Алания` | ru | 16 | 0 | 16 | Q133268406 member of the Parliament of North Ossetia–Alania | upstream |
| `Депутаты Государственного Совета Чувашской Республики` | ru | 16 | 0 | 16 | Q133268356 Member of the State Council of the Chuvash Republic | upstream |
| `Депутаты Законодательного собрания Ростовской области` | ru | 17 | 0 | 17 | Q133268385 member of the Legislative Assembly of Rostov Oblast | upstream |
| `21st-century_members_of_the_Yukon_Legislative_Assembly` | en | 79 | 61 | 18 | Q18608478 member of the Yukon Legislative Assembly | upstream |
| `Депутаты Государственного совета Крыма` | ru | 18 | 0 | 18 | Q133268428 Member of the State Council of the Republic of Crimea | upstream |
| `Депутаты Законодательного собрания Ленинградской области` | ru | 18 | 0 | 18 | Q133268377 Member of the Legislative Assembly of Leningrad Oblast | upstream |
| `Депутаты Законодательной думы Томской области` | ru | 18 | 0 | 18 | Q133268360 Member of the Legislative Duma of Tomsk Oblast | upstream |
| `Депутаты Верховного хурала (парламента) Республики Тыва` | ru | 18 | 0 | 18 | Q133268346 member of the Great Khural of Tuva | upstream |
| `Депутаты Законодательного собрания Пензенской области` | ru | 19 | 0 | 19 | Q133268378 Member of the Legislative Assembly of Penza Oblast | upstream |
| `Vice_presidents_of_Ecuador` | en | 39 | 18 | 21 | Q4261569 Vice President of Ecuador | upstream |
| `Депутаты Законодательного собрания Красноярского края` | ru | 21 | 0 | 21 | Q133268376 Member of the Legislative Assembly of Krasnoyarsk Krai | upstream |
| `Депутаты Думы Ставропольского края` | ru | 21 | 0 | 21 | Q133268359 Member of the Regional Parliament of Stavropol Krai | upstream |
| `Депутаты Законодательного собрания Челябинской области` | ru | 22 | 0 | 22 | Q133268386 Member of the Legislative Assembly of Chelyabinsk Oblast | upstream |
| `Депутаты Воронежской областной думы` | ru | 24 | 1 | 23 | Q133268348 Member of the Voronezh Oblast Duma | upstream |
| `21st-century_members_of_the_Legislative_Assembly_of_New_Brunswick` | en | 197 | 173 | 24 | Q18984329 member of the Legislative Assembly of New Brunswick | upstream |
| `Депутаты Саратовской областной думы` | ru | 25 | 1 | 24 | Q133268412 member of the Saratov Oblast Duma | upstream |
| `Депутаты Смоленской областной думы` | ru | 24 | 0 | 24 | Q133268414 Member of the Smolensk Oblast Duma | upstream |
| `Депутаты Государственного Собрания (Ил Тумэн) Республики Саха (Якутия)` | ru | 24 | 0 | 24 | Q133268316 Member of the State Assembly of the Sakha Republic | upstream |
| `Депутаты Народного Хурала Республики Бурятии` | ru | 25 | 0 | 25 | Q133268401 member of the People's Khural of the Republic of Buryatia | upstream |
| `Депутаты Самарской Губернской думы` | ru | 27 | 0 | 27 | Q133268410 member of the Samara Regional Duma | upstream |
| `Presidents_of_the_European_Council` | en | 32 | 3 | 29 | Q735587 President of the European Council | review |
| `Депутаты Законодательного собрания Свердловской области` | ru | 29 | 0 | 29 | Q133268383 Member of the Legislative Assembly of Sverdlovsk Oblast | upstream |
| `Vicepresidentes_de_Ecuador` | es | 51 | 19 | 32 | Q4261569 Vice President of Ecuador | upstream |
| `Депутаты Законодательного собрания Краснодарского края` | ru | 32 | 0 | 32 | Q133268363 Member of the Legislative Assembly of Krasnodar Krai | upstream |
| `Presidents_of_the_United_Nations_General_Assembly` | en | 79 | 46 | 33 | Q1161813 President of the United Nations General Assembly | review |
| `Депутаты Законодательного собрания Нижегородской области` | ru | 33 | 0 | 33 | Q133268374 Member of the Legislative Assembly of Nizhny Novgorod Region | upstream |
| `Депутаты Законодательного собрания Пермского края` | ru | 33 | 0 | 33 | Q133268384 member of the Legislative Assembly of Perm Krai | upstream |
| `21st-century_members_of_the_Legislative_Assembly_of_Alberta` | en | 365 | 331 | 34 | Q15964815 member of Alberta Legislative Assembly | upstream |
| `Presidents_of_the_Congress_of_Deputies_(Spain)` | en | 70 | 32 | 38 | Q17014422 President of the Congress of Deputies | upstream |
| `Депутаты Законодательного собрания Санкт-Петербурга` | ru | 51 | 1 | 50 | Q111242469 Member of the Legislative Assembly of Saint Petersburg | upstream |
| `21st-century_members_of_the_Legislative_Assembly_of_the_Northwest_Territories` | en | 71 | 13 | 58 | Q45308871 Member of the Legislative Assembly of the Northwest Territories | upstream |
| `21st-century_members_of_the_Legislative_Assembly_of_Saskatchewan` | en | 190 | 128 | 62 | Q18675661 Member of the Legislative Assembly of Saskatchewan | upstream |
| `Депутаты Государственного Совета Республики Татарстан` | ru | 72 | 0 | 72 | Q133268355 Member of the State Council of the Republic of Tatarstan | upstream |
| `21st-century_members_of_the_Legislative_Assembly_of_Prince_Edward_Island` | en | 99 | 26 | 73 | Q21010685 member of the Legislative Assembly of Prince Edward Island | upstream |
| `21st-century_members_of_the_Legislative_Assembly_of_Ontario` | en | 382 | 272 | 110 | Q3305347 member of the Ontario Provincial Parliament | upstream |
| `Члены Совета безопасности России` | ru | 124 | 5 | 119 | Q38715670 Permanent member of the Security Council of Russia | upstream |
| `21st-century_members_of_the_Legislative_Assembly_of_Manitoba` | en | 181 | 57 | 124 | Q19007867 member of the Legislative Assembly of Manitoba | upstream |
| `21st-century_members_of_the_Newfoundland_and_Labrador_House_of_Assembly` | en | 172 | 12 | 160 | Q19403853 member of the Newfoundland and Labrador House of Assembly | upstream |
| `21st-century_members_of_the_Legislative_Assembly_of_British_Columbia` | en | 339 | 105 | 234 | Q19004821 member of the Legislative Assembly of British Columbia | upstream |

## `bucket` (24 specs)

The position names a *class* of offices, not one seat, so there is no single item to verify against. Needs the per-person gazetteer pass.

| category | lang | members | holds | gap | target | why |
|---|---|---:|---:|---:|---|---|
| `United_States_presidential_advisors` | en | 0 | 0 | 0 | None |  |
| `Alcaldes_de_Venezuela` | es | 0 | 0 | 0 | None |  |
| `Alcaldes_de_Nicaragua` | es | 0 | 0 | 0 | None |  |
| `Alcaldes_de_Guatemala` | es | 0 | 0 | 0 | None |  |
| `Ministři_vlád_České_republiky` | en | 0 | 0 | 0 | Q68081922 ministr vlády České republiky |  |
| `Government_ministers_of_Spain` | en | 0 | 0 | 0 | Q20899145 minister of Spain |  |
| `Mayors_of_places_in_Spain` | en | 0 | 0 | 0 | Q5663900 alcalde |  |
| `List_of_serving_general_and_flag_officers_of_the_Singapore_Armed_Forces` | en | 0 | 0 | 0 | None |  |
| `New_South_Wales_local_councillors` | en | 0 | 0 | 0 | None |  |
| `Northern_Territory_local_councillors` | en | 0 | 0 | 0 | None |  |
| `Victoria_(state)_local_councillors` | en | 0 | 0 | 0 | None |  |
| `Queensland_local_councillors` | en | 0 | 0 | 0 | None |  |
| `Western_Australian_local_councillors` | en | 0 | 0 | 0 | None |  |
| `South_Australian_local_councillors` | en | 0 | 0 | 0 | None |  |
| `Tasmanian_local_councillors` | en | 0 | 0 | 0 | None |  |
| `Министры Российской Федерации` | ru | 0 | 0 | 0 | Q15620328 federal minister of Russia |  |
| `Первое правительство Медведева` | ru | 0 | 0 | 0 | Q15620328 federal minister of Russia |  |
| `Второе правительство Медведева` | ru | 0 | 0 | 0 | None |  |
| `Правительство Зубкова` | ru | 0 | 0 | 0 | None |  |
| `Действующие главы регионов России` | ru | 0 | 0 | 0 | None |  |
| `Главы парламентов субъектов Российской Федерации` | ru | 0 | 0 | 0 | None |  |
| `Главы муниципальных образований` | ru | 0 | 0 | 0 | Q4139102 head of municipality | upstream |
| `Главы районов России` | ru | 0 | 0 | 0 | Q4139102 head of municipality | upstream |
| `Руководители политических партий России` | ru | 0 | 0 | 0 | None |  |

## `unresolved` (28 specs)

No `wikidata_id` resolved yet — see `tasks/category_positions.md`.

| category | lang | members | holds | gap | target | why |
|---|---|---:|---:|---:|---|---|
| `Members_of_the_Congress_of_Colombia` | en | 0 | 0 | 0 | None |  |
| `Soudci_Nejvyššího_soudu_České_republiky` | en | 0 | 0 | 0 | None |  |
| `Soudci_Nejvyššího_správního_soudu_České_republiky` | en | 0 | 0 | 0 | None |  |
| `Presidents_of_the_autonomous_communities_of_Spain` | en | 0 | 0 | 0 | None |  |
| `Депутаты Думы Корякского автономного округа` | ru | 0 | 0 | 0 | None |  |
| `Депутаты Законодательного собрания (Суглана) Эвенкийского автономного округа` | ru | 1 | 0 | 1 | None |  |
| `Registrars_of_the_International_Criminal_Court` | en | 5 | 0 | 5 | None |  |
| `Executive_Directors_of_the_World_Food_Programme` | en | 7 | 0 | 7 | None |  |
| `Presidents_of_the_National_Congress_(Ecuador)` | en | 8 | 0 | 8 | None |  |
| `LR_generalinio_prokuroro_pavaduotojai` | lt | 10 | 0 | 10 | None |  |
| `Bank_for_International_Settlements` | en | 12 | 0 | 12 | None |  |
| `Депутаты Свердловской областной думы` | ru | 13 | 0 | 13 | None |  |
| `Presidents_of_the_Senate_of_Ecuador` | en | 17 | 0 | 17 | None |  |
| `Судьи Высшего арбитражного суда Российской Федерации` | ru | 17 | 0 | 17 | None |  |
| `Члены совета директоров «Газпрома»` | ru | 18 | 0 | 18 | None |  |
| `Members_of_the_State_Administration_Council` | en | 19 | 0 | 19 | None |  |
| `Заместители председателя Совета Федерации России` | ru | 20 | 0 | 20 | None |  |
| `Сотрудники Службы внешней разведки России` | ru | 21 | 0 | 21 | None |  |
| `Lietuvos_vyriausiojo_administracinio_teismo_teisėjai` | lt | 25 | 0 | 25 | None |  |
| `Судьи Верховного суда Российской Федерации` | ru | 27 | 0 | 27 | None |  |
| `Presidentes_del_Congreso_Nacional_de_Ecuador` | es | 30 | 0 | 30 | None |  |
| `LR_Konstitucinio_Teismo_teisėjai` | lt | 30 | 0 | 30 | None |  |
| `Члены ЛДПР` | ru | 35 | 0 | 35 | None |  |
| `Судьи Конституционного суда Российской Федерации` | ru | 36 | 0 | 36 | None |  |
| `General_People's_Congress_(Yemen)_politicians` | en | 42 | 0 | 42 | None |  |
| `Lietuvos_Aukščiausiojo_Teismo_teisėjai` | lt | 72 | 0 | 72 | None |  |
| `Председатели комитетов Государственной думы Российской Федерации` | ru | 93 | 0 | 93 | None |  |
| `Члены «Единой России»` | ru | 1847 | 0 | 1847 | None |  |

## `broken-query` (24 specs)

The category matches no page at all: a wrong wiki, or a title whose case is wrong after the first letter. `scripts/category_langcheck.py` found these. The fix is the query, not the position — and until it is fixed the spec contributes nobody, so it cannot be called retirable.

| category | lang | members | holds | gap | target | why |
|---|---|---:|---:|---:|---|---|
| `Under-Secretaries-General_of_the_United_Nations` | en | 0 | 0 | 0 | Q2932400 Under-Secretary-General of the United Nations |  |
| `OSCE_Secretaries_General` | en | 0 | 0 | 0 | Q110934652 Secretary General of the Organization for Security and Co-operation in Europe | review |
| `Council_of_Europe_Secretaries-General` | en | 0 | 0 | 0 | Q2942251 Secretary General of the Council of Europe | review |
| `World_Health_Organization_director-generals` | en | 0 | 0 | 0 | Q62070236 Director-General of the World Health Organization | review |
| `Current_justices_of_the_Supreme_Court_of_the_United_States` | en | 0 | 0 | 0 | Q20706330 United States Supreme Court justice |  |
| `White_House_Counsels` | en | 0 | 0 | 0 | Q1296423 White House Counsel | upstream |
| `Members_of_the_Senate_of_Poland_2023–2027` | pl | 0 | 0 | 0 | Q81747225 Member of the Senate of the Republic of Poland |  |
| `Poslanci_Parlamentu_České_republiky_(2021–2025)` | en | 0 | 0 | 0 | Q19803234 Member of the Chamber of Deputies of the Parliament of the Czech Republic |  |
| `Poslanci_Parlamentu_České_republiky` | en | 0 | 0 | 0 | Q19803234 Member of the Chamber of Deputies of the Parliament of the Czech Republic |  |
| `Senátoři_Parlamentu_České_republiky` | en | 0 | 0 | 0 | Q18941264 Member of the Senate of the Parliament of the Czech Republic |  |
| `Prezidenti_České_republiky` | en | 0 | 0 | 0 | Q1819381 President of the Czech Republic |  |
| `Soudci_Ústavního_soudu_České_republiky` | en | 0 | 0 | 0 | Q59773473 judge of the Constitutional Court of the Czech Republic | upstream |
| `Deputy_Prime_Ministers_of_Spain` | en | 0 | 0 | 0 | Q3113035 Deputy Prime Minister of Spain |  |
| `Members_of_the_German_Bundesrat` | en | 0 | 0 | 0 | Q15835370 Member of the Bundesrat of Germany |  |
| `Депутаты Белгородской областной Думы` | ru | 0 | 0 | 0 | Q133268343 Member of the Belgorod Oblast Duma | upstream |
| `Депутаты Брянской областной Думы` | ru | 0 | 0 | 0 | Q133268434 Member of the Bryansk Oblast Duma | upstream |
| `Депутаты Волгоградской областной Думы` | ru | 0 | 0 | 0 | Q101483020 Member of the Volgograd Regional Duma |  |
| `Депутаты Законодательного Собрания Забайкальского края` | ru | 0 | 0 | 0 | Q133268368 Member of the Legislative Assembly of Zabaykalsky Krai | upstream |
| `Депутаты Ивановской областной Думы` | ru | 0 | 0 | 0 | Q133268390 member of the Ivanovo Oblast Duma | upstream |
| `Депутаты Костромской областной Думы` | ru | 0 | 0 | 0 | Q133268393 Member of the Kostroma Oblast Duma | upstream |
| `Депутаты Курганской областной Думы` | ru | 0 | 0 | 0 | Q133268421 Member of the Kurgan Oblast Duma | upstream |
| `Депутаты Мурманской областной Думы` | ru | 0 | 0 | 0 | Q133268397 Member of the Murmansk Oblast Duma | upstream |
| `Депутаты Рязанской областной Думы` | ru | 0 | 0 | 0 | Q133268409 Member of the Ryazan Oblast Duma | upstream |
| `Депутаты Тюменской областной Думы` | ru | 0 | 0 | 0 | Q62653950 Member of the Tyumen Oblast Duma |  |

