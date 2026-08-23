# PETScan queries that can be deleted

The checklist for a PR against
`opensanctions/datasets/_wikidata/categories/wd_categories.yml`. A query
belongs here when its target is a position `wd_peps` emits **and** every
member of its category either already holds that position or is someone no
PEP dataset would emit anyway.

Maintained by `scripts/retirable.py`; 44 removable, 50 still carrying work. Rows accumulate — a spec keeps its
`first measured` date, so this is a record rather than a snapshot.

**What deletion costs.** Removing a whole spec removes its `topic:`, so the
people in the `drops` column leave OpenSanctions: they are the long-dead and
the pre-1920, whom `wd_peps` declines by design. That is a correction, not a
regression — but it is a dataset change, and the number is stated per row so
a reviewer can weigh it rather than discover it.

## Removable

| category | lang | members | hold it | drops | target | first measured |
|---|---|---:|---:|---:|---|---|
| `21st-century_members_of_the_House_of_Commons_of_Canada` | en | 1179 | 1179 | 0 | Q15964890 member of the House of Commons of Canada | 2026-08-23 |
| `Депутаты Государственной думы Российской Федерации VII созыва` | ru | 498 | 498 | 0 | Q17276321 member of the State Duma | 2026-08-23 |
| `Országgyűlési_képviselők_(2022–2026)` | hu | 209 | 209 | 0 | Q17590876 member of the National Assembly of Hungary | 2026-08-23 |
| `Members_of_the_National_Assembly_of_Hungary_(2022–2026)` | en | 172 | 172 | 0 | Q17590876 member of the National Assembly of Hungary | 2026-08-23 |
| `Australian_MPs_2022–2025` | en | 155 | 155 | 0 | Q18912794 member of the Australian House of Representatives | 2026-08-23 |
| `Presidents_of_Nicaragua` | en | 68 | 66 | 2 | Q852448 President of Nicaragua | 2026-08-23 |
| `Presidentes_de_Nicaragua` | es | 67 | 65 | 2 | Q852448 President of Nicaragua | 2026-08-23 |
| `Presidentes_de_Colombia` | es | 106 | 61 | 45 | Q853475 President of Colombia | 2026-08-23 |
| `Presidents_of_Venezuela` | en | 52 | 50 | 2 | Q11942698 President of Venezuela | 2026-08-23 |
| `Presidentes_de_Guatemala` | es | 50 | 48 | 2 | Q6085537 president of Guatemala | 2026-08-23 |
| `Presidents_of_the_United_States` | en | 45 | 45 | 0 | Q11696 President of the United States | 2026-08-23 |
| `Presidents_of_the_Senate_of_Spain` | en | 39 | 36 | 3 | Q1335465 President of the Spanish Senate | 2026-08-23 |
| `Presidents_of_Colombia` | en | 38 | 31 | 7 | Q853475 President of Colombia | 2026-08-23 |
| `Members_of_the_Senate_of_Venezuela` | en | 33 | 30 | 3 | Q20081434 senator of Venezuela | 2026-08-23 |
| `Presidentes_de_Venezuela` | es | 31 | 29 | 2 | Q11942698 President of Venezuela | 2026-08-23 |
| `Presidents_of_Guatemala` | en | 25 | 21 | 4 | Q6085537 president of Guatemala | 2026-08-23 |
| `Lietuvos_ministrai_pirmininkai` | lt | 19 | 18 | 1 | Q845439 Prime Minister of Lithuania | 2026-08-23 |
| `Chief_justices_of_the_United_States` | en | 17 | 17 | 0 | Q11147 Chief Justice of the United States | 2026-08-23 |
| `Mayors_of_Bogotá` | en | 28 | 16 | 12 | Q21994938 Mayor of Bogota | 2026-08-23 |
| `Secretaries_general_of_NATO` | en | 17 | 16 | 1 | Q167662 Secretary General of NATO | 2026-08-23 |
| `Prime_ministers_of_Spain` | en | 116 | 15 | 101 | Q844587 Prime Minister of Spain | 2026-08-23 |
| `Депутаты Думы Ханты-Мансийского автономного округа — Югры` | ru | 13 | 13 | 0 | Q124755389 Deputy of the Duma of Khanty-Mansi Autonomous Okrug — Yugra | 2026-08-23 |
| `Члены Совета Федерации России от Рязанской области` | ru | 14 | 13 | 1 | Q4516946 member of the Federation Council of Russia | 2026-08-23 |
| `Председатели Правительства РФ` | ru | 12 | 12 | 0 | Q842386 Prime Minister of Russia | 2026-08-23 |
| `Prime_ministers_of_Belarus` | en | 17 | 11 | 6 | Q12379704 Prime Minister of Belarus | 2026-08-23 |
| `Члены Совета Федерации России от Приморского края` | ru | 11 | 10 | 1 | Q4516946 member of the Federation Council of Russia | 2026-08-23 |
| `Foreign_ministers_of_Belarus` | en | 10 | 9 | 1 | Q2045068 Minister of Foreign Affairs of Belarus | 2026-08-23 |
| `Defence_ministers_of_Belarus` | en | 7 | 7 | 0 | Q44035369 Defence Minister of Belarus | 2026-08-23 |
| `Justice_ministers_of_Belarus` | en | 7 | 7 | 0 | Q106510814 Minister of Justice of the Republic of Belarus | 2026-08-23 |
| `Mayors_of_Guatemala_City` | en | 9 | 7 | 2 | Q116790781 Mayor of Guatemala | 2026-08-23 |
| `Lietuvos_kariuomenės_vadai` | lt | 16 | 7 | 9 | Q55607326 Chief of Defence of Lithuania | 2026-08-23 |
| `Interior_ministers_of_Belarus` | en | 6 | 5 | 1 | Q100699741 Minister of Internal Affairs of the Republic of Belarus | 2026-08-23 |
| `Secretaries-general_of_the_Gulf_Cooperation_Council` | en | 5 | 5 | 0 | Q104127429 Secretary-General of the Gulf Cooperation Council | 2026-08-23 |
| `Lietuvos_banko_vadovai` | lt | 10 | 5 | 5 | Q109496871 Governor of the Bank of Lithuania | 2026-08-23 |
| `Health_ministers_of_Belarus` | en | 4 | 4 | 0 | Q89775465 Minister of Health of the Republic of Belarus | 2026-08-23 |
| `Industry_ministers_of_Belarus` | en | 4 | 4 | 0 | Q106508605 Minister of Industry of the Republic of Belarus | 2026-08-23 |
| `Lietuvos_prezidentai` | lt | 4 | 4 | 0 | Q878222 President of the Republic of Lithuania | 2026-08-23 |
| `Председатели Совета Федерации России` | ru | 4 | 4 | 0 | Q4376672 Chairman of the Federation Council of Russia | 2026-08-23 |
| `Члены Совета Федерации России от Камчатского края` | ru | 4 | 4 | 0 | Q4516946 member of the Federation Council of Russia | 2026-08-23 |
| `Finance_ministers_of_Belarus` | en | 3 | 3 | 0 | Q106510813 Minister of Finance of the Republic of Belarus | 2026-08-23 |
| `Information_ministers_of_Belarus` | en | 3 | 3 | 0 | Q106399613 Minister of Information of the Republic of Belarus | 2026-08-23 |
| `Transport_ministers_of_Belarus` | en | 2 | 2 | 0 | Q60676745 Minister of Transport and Communications of the Republic of Belarus | 2026-08-23 |
| `Members_of_the_Bundestag` | en | 1 | 1 | 0 | Q1939555 member of the German Bundestag | 2026-08-23 |
| `Senadores_de_Colombia` | es | 0 | 0 | 0 | Q19254253 member of the Senate of Colombia | 2026-08-23 |

Total: **44 queries**, 2917 people already covered by real P39 statements, 213 leaving the dataset.

### The categories to delete

```
en:21st-century_members_of_the_House_of_Commons_of_Canada
ru:Депутаты Государственной думы Российской Федерации VII созыва
hu:Országgyűlési_képviselők_(2022–2026)
en:Members_of_the_National_Assembly_of_Hungary_(2022–2026)
en:Australian_MPs_2022–2025
en:Presidents_of_Nicaragua
es:Presidentes_de_Nicaragua
es:Presidentes_de_Colombia
en:Presidents_of_Venezuela
es:Presidentes_de_Guatemala
en:Presidents_of_the_United_States
en:Presidents_of_the_Senate_of_Spain
en:Presidents_of_Colombia
en:Members_of_the_Senate_of_Venezuela
es:Presidentes_de_Venezuela
en:Presidents_of_Guatemala
lt:Lietuvos_ministrai_pirmininkai
en:Chief_justices_of_the_United_States
en:Mayors_of_Bogotá
en:Secretaries_general_of_NATO
en:Prime_ministers_of_Spain
ru:Депутаты Думы Ханты-Мансийского автономного округа — Югры
ru:Члены Совета Федерации России от Рязанской области
ru:Председатели Правительства РФ
en:Prime_ministers_of_Belarus
ru:Члены Совета Федерации России от Приморского края
en:Foreign_ministers_of_Belarus
en:Defence_ministers_of_Belarus
en:Justice_ministers_of_Belarus
en:Mayors_of_Guatemala_City
lt:Lietuvos_kariuomenės_vadai
en:Interior_ministers_of_Belarus
en:Secretaries-general_of_the_Gulf_Cooperation_Council
lt:Lietuvos_banko_vadovai
en:Health_ministers_of_Belarus
en:Industry_ministers_of_Belarus
lt:Lietuvos_prezidentai
ru:Председатели Совета Федерации России
ru:Члены Совета Федерации России от Камчатского края
en:Finance_ministers_of_Belarus
en:Information_ministers_of_Belarus
en:Transport_ministers_of_Belarus
en:Members_of_the_Bundestag
es:Senadores_de_Colombia
```

## Still carrying work

The target emits, but members are missing the statement. These are the
enrichment loop's queue; each becomes removable when `todo` reaches zero.

| category | lang | hold it | todo | target |
|---|---|---:|---:|---|
| `Депутаты Государственной думы Российской Федерации от одномандатных округов` | ru | 866 | 3 | Q17276321 member of the State Duma |
| `Члены Совета Федерации России (с 2000)` | ru | 730 | 47 | Q4516946 member of the Federation Council of Russia |
| `Seimo_nariai` | lt | 664 | 4 | Q18507240 Member of the Seimas |
| `Members_of_the_Australian_Senate` | en | 656 | 1 | Q6814428 member of the Australian Senate |
| `Депутаты Государственной думы Российской Федерации VIII созыва` | ru | 463 | 10 | Q17276321 member of the State Duma |
| `Members_of_the_House_of_Representatives_(Netherlands)` | en | 419 | 2 | Q18887908 member of the House of Representatives of the Netherlands |
| `Posłowie_na_Sejm_Rzeczypospolitej_Polskiej_X_kadencji` | pl | 391 | 106 | Q19269361 member of the Sejm |
| `Diputados_de_la_LXV_Legislatura_de_México` | es | 335 | 3 | Q18534310 Member of the Chamber of Deputies of Mexico |
| `Members_of_the_Senate_(Netherlands)` | en | 309 | 1 | Q19305384 member of the Senate of the Netherlands |
| `21st-century_members_of_the_Senate_of_Canada` | en | 293 | 6 | Q18524027 member of the Senate of Canada |
| `Diputados_de_la_LXIV_Legislatura_de_México` | es | 285 | 2 | Q18534310 Member of the Chamber of Deputies of Mexico |
| `Members_of_the_Polish_Sejm_2023–2027` | en | 280 | 64 | Q19269361 member of the Sejm |
| `Члены Совета Федерации России (1996—2000)` | ru | 198 | 55 | Q4516946 member of the Federation Council of Russia |
| `Senadores_de_las_LXIV_y_LXV_Legislaturas_de_México` | es | 140 | 27 | Q19971999 member of the Senate of Mexico |
| `Members_of_the_Senate_of_Spain` | en | 124 | 10 | Q19323171 member of the Senate of Spain |
| `13._Saeimas_deputāti` | lv | 122 | 4 | Q21191589 deputy of Saeima |
| `Депутаты Совета Федерации России (1993—1995)` | ru | 111 | 47 | Q4516946 member of the Federation Council of Russia |
| `Заместители председателя Правительства Российской Федерации` | ru | 67 | 9 | Q14805701 Deputy Chairman of the Government of the Russian Federation |
| `Members_of_the_Supreme_People's_Assembly` | en | 66 | 61 | Q21328639 member of the Supreme People's Assembly |
| `Members_of_the_National_Congress_(Ecuador)` | en | 49 | 17 | Q22230757 National Congress Deputy |
| `Members_of_the_Congress_of_Guatemala` | en | 47 | 11 | Q18277108 Member of the Congress of Guatemala |
| `14._Saeimas_deputāti` | lv | 45 | 84 | Q21191589 deputy of Saeima |
| `Members_of_the_Congress_of_Deputies_(Spain)` | en | 43 | 1 | Q18171345 Member of the Congress of Deputies |
| `Presidents_of_Ecuador` | en | 43 | 1 | Q732562 President of Ecuador |
| `Senadores_de_las_LXVI_y_LXVII_Legislaturas_de_México` | es | 42 | 81 | Q19971999 member of the Senate of Mexico |
| `Presidentes_de_Ecuador` | es | 38 | 2 | Q732562 President of Ecuador |
| `Diputados_de_Guatemala` | es | 32 | 12 | Q18277108 Member of the Congress of Guatemala |
| `Poslanci_NR_SR_(2020_–_2023)` | sk | 31 | 62 | Q19967563 Member of the National Council of the Slovak Republic |
| `Members_of_the_National_Council_(Slovakia)_2023–2027` | en | 21 | 50 | Q19967563 Member of the National Council of the Slovak Republic |
| `Members_of_the_National_Assembly_(Nicaragua)` | en | 19 | 8 | Q18616113 Member of the National Assembly of Nicaragua |
| `Первые заместители председателя Правительства Российской Федерации` | ru | 18 | 5 | Q1965788 First Deputy Chairman of the Government of the Russian Federation |
| `Senatorowie_XI_kadencji_Senatu_Rzeczypospolitej_Polskiej` | pl | 17 | 85 | Q81747225 Member of the Senate of the Republic of Poland |
| `Members_of_the_National_Assembly_(Ecuador)` | en | 16 | 87 | Q21295982 Member of the National Assembly of Ecuador |
| `Депутаты Московской городской думы` | ru | 14 | 38 | Q96324124 member of the Moscow City Duma |
| `Deputy_prime_ministers_of_Belarus` | en | 12 | 16 | Q18690228 Deputy Prime Minister of the Republic of Belarus |
| `Члены Совета Федерации России от Волгоградской области` | ru | 12 | 2 | Q4516946 member of the Federation Council of Russia |
| `Members_of_the_Hellenic_Parliament` | en | 11 | 2 | Q18915989 member of the Hellenic Parliament |
| `Secretaries-general_of_the_United_Nations` | en | 10 | 1 | Q81066 United Nations Secretary-General |
| `Члены Совета Федерации России от Хабаровского края` | ru | 9 | 1 | Q4516946 member of the Federation Council of Russia |
| `Lietuvos_generaliniai_prokurorai` | lt | 7 | 1 | Q132068652 Prosecutor General of Lithuania |
| `Руководители Аппарата Правительства Российской Федерации` | ru | 7 | 9 | Q107883642 Chief of the Government Staff |
| `Asambleístas_y_diputados_de_Ecuador` | es | 5 | 117 | Q21295982 Member of the National Assembly of Ecuador |
| `Мэры Москвы` | ru | 3 | 1 | Q1837906 mayor of Moscow |
| `Члены Совета Федерации России от Республики Крым` | ru | 3 | 1 | Q4516946 member of the Federation Council of Russia |
| `Депутаты Государственного Совета Удмуртской Республики` | ru | 2 | 14 | Q108610448 Deputy of the State Council of the Udmurt Republic |
| `Communications_ministers_of_Belarus` | en | 1 | 2 | Q28598480 Minister of Communications and Informatization of the Republic of Belarus |
| `Депутаты Народного собрания Дагестана` | ru | 1 | 32 | Q115242140 member of the People's Assembly of the Republic of Dagestan |
| `Mayors_of_Managua` | en | 0 | 6 | Q104881755 Mayor of Managua |
| `Депутаты Московской областной думы` | ru | 0 | 33 | Q110805962 Member of Moscow Oblast Duma |
| `Депутаты Парламента Чеченской Республики` | ru | 0 | 10 | Q133268407 Member of the Parliament of the Chechen Republic |
