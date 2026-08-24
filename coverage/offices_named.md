# Offices the enrichment loop named

Measured 2026-08-24 by `scripts/office_ledger.py` over every run under `data/enrich/`.

A run's gazetteer holds the office its spec names and, for a
single-target spec, nothing else — so **every other office a person
turns out to have held** reads as unresolved by construction.
`wd/positions.py:lookup_position` places what it can; what is left is a
creation queue with evidence attached, which is the thing
`tasks/category_positions.md` has wanted since 2026-08-05.

One row per office, merged across the runs that named it: an item is
created per office, and two specs naming the same one is corroboration
rather than two jobs.

| disposition | offices | with an attested holder |
|---|---:|---:|
| `create` | 79 | 29 |
| `ambiguous` | 6 | 5 |
| `no-polity` | 4 | 1 |
| `placed` | 14 | 0 |

## `create` (79)

**No item exists.** This is the queue: each row names an office, a person attested to have held it, the dates, and the sentence that says so. `wd/create.py:guard` still applies — a duplicate search, a holder floor and a body-label check — but the holder floor is already met, which is what nine campaigns' creation lists never had.

* **Mayor of Włoszczowa (burmistrz Włoszczowy)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11687458 2006–2010 — “w latach 2006–2010 oraz 2010–2014 burmistrz Włoszczowy”
  * Q11687458 2010–2014 — “w latach 2006–2010 oraz 2010–2014 burmistrz Włoszczowy”
* **Member of the Central American Parliament**  ·  `en_Members_of_the_Congress_of_Guatemal`
  * Q119998687 2020-01-14–2024-01-14 — “She served a member of the Central American Parliament for the National Unity of Hope from 2020 to 2024”
  * Q122466002 2024 — “she is member of the Central American Parliament for Guatemala since 2024, having been elected in 2023 general election”
* **Minister of Public Finance of Guatemala**  ·  `en_Members_of_the_Congress_of_Guatemal`, `es_Diputados_de_Guatemala`
  * Q60970569 2016-01–2018-09 — “Ejerció de ministro de Finanzas Públicas entre enero de 2016 y septiembre de 2018.”
  * Q61978364 2024-01-19 — “Minister of Public Finance since January 19, 2024”
* **Chief Labour Inspector (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11688711 2006-03-15–2008-08-21 — “Chief Labour Inspector — 2006-03-15–2008-08-21”
* **Councillor of the City of Warsaw (radna m.st. Warszawy)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q101084325 2018–2023 — “W 2018 z listy Koalicji Obywatelskiej została wybrana do Rady m.st. Warszawy”
* **Councillor of the Sejmik of Świętokrzyskie Voivodeship (radny sejmiku świętokrzyskiego)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11687458 2014 — “Bartłomiej Dorywalski uzyskał natomiast mandat radnego sejmiku świętokrzyskiego V kadencji.”
* **Deputy Voivode of Świętokrzyskie Voivodeship (wicewojewoda świętokrzyski)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11687458 2018-11-27–2019 — “27 listopada 2018 został powołany na stanowisko wicewojewody świętokrzyskiego.”
* **Director of the National Civil Police of Guatemala**  ·  `es_Diputados_de_Guatemala`
  * Q124318743 2015–2018 — “director de la Policía Nacional Civil de 2015 a 2018”
* **First Vice President of the Congress of Guatemala**  ·  `en_Members_of_the_Congress_of_Guatemal`
  * Q124318743 2026-01-14 — “First Vice President of the Congress — 2026-01-14”
* **First Vice President of the Congress of the Republic of Guatemala**  ·  `es_Diputados_de_Guatemala`
  * Q124318743 2026-01-14 — “First Vice President of the Congress — 2026-01-14”
* **Marshal of Warmian–Masurian Voivodeship**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11715524 2006-11-29–2014-12-12 — “He served as marshal of Warmian–Masurian Voivodeship from 2006 to 2014”
* **Mayor of Chełm**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11749225 2002–2006 — “From 2002 to 2006, he served as mayor of Chełm.”
* **Minister of Family, Labour and Social Policy (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11688711 2019-06-04–2019-11-15 — “Minister of Family, Labour and Social Policy — 2019-06-04–2019-11-15”
* **President of the Central American Parliament**  ·  `en_Members_of_the_Congress_of_Guatemal`
  * Q119998687 2020-01-15–2020-08-28 — “President of the Central American Parliament — 2020-01-15–2020-08-28”
* **Przewodniczący sejmiku województwa lubelskiego (Chairman of the Lublin Voivodeship Sejmik)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11715257 2007-12-20–2010 — “przewodniczący sejmiku lubelskiego (2007–2010)”
* **Secretary of State in the Ministry of Agriculture and Rural Development (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q108391916 2023-12-13–2025-06-18 — “{{start date|2023|12|13|df=y}} – {{end date|2025|06|18|df=y}}”
* **Secretary of State in the Ministry of Funds and Regional Policy (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11715524 2023-12–2024 — “Im Dezember 2023 wurde er zum Staatssekretär im Ministerium für Fonds und Regionalpolitik ernannt.”
* **Secretary of State in the Ministry of Infrastructure and Construction (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11738333 2015-11-20–2018 — “w latach 2015–2018 sekretarz stanu w Ministerstwie Infrastruktury i Budownictwa”
* **Secretary of State in the Ministry of Sport and Tourism (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11715493 2019-06–2023 — “W czerwcu 2019 został powołany na stanowisko sekretarza stanu w Ministerstwie Sportu i Turystyki”
* **Secretary of State in the Ministry of the Environment (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11694886 2015-06-16–2015-11-11 — “On June 16, 2015, she was appointed Secretary of State in the Ministry of the Environment. She held this position until November 11, 2015.”
* **Secretary of State of the Ministry of Development Funds and Regional Policy (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11715355 2024-06-26 — “On 26 June 2024, he became the Secretary of State of the Ministry of Development Funds and Regional Policy”
* **Sekretarz stanu w Ministerstwie Finansów (Secretary of State in the Ministry of Finance of Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11720108 2013–2015 — “w latach 2013–2015 sekretarz stanu w Ministerstwie Finansów”
* **Sekretarz stanu w Ministerstwie Rolnictwa i Rozwoju Wsi (Secretary of State in the Ministry of Agriculture and Rural Development, Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11715257 2023-12 — “W grudniu 2023 został sekretarzem stanu w Ministerstwie Rolnictwa i Rozwoju Wsi.”
* **Third Vice President of the Congress of Guatemala**  ·  `en_Members_of_the_Congress_of_Guatemal`, `es_Diputados_de_Guatemala`
  * Q117805648 2020–2022 — “Castillo was elected as the third vice president of Congress during the presidency of Allan Rodríguez”
* **Vice-Marshal of Podlaskie Voivodeship**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q111249780 2022-03-03–2023 — “On March 3, 2022, he took over as vice-marshal of the Podlaskie Voivodeship”
* **Vice-Minister of Foreign Affairs of Guatemala**  ·  `en_Members_of_the_Congress_of_Guatemal`
  * Q38058073 2016-02 — “Fue nombrada Viceministra de Relaciones Exteriores, en febrero de 2016.”
* **Voivode of the Masovian Voivodeship**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11715561 2007-02-01–2007-11-29 — “Voivode of Masovian Voivodeship — 2007-02-01–2007-11-29”
* **city councillor of Szczecin**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q111365600 2018–2023 — “From 2018 to 2023, he was a city councillor of Szczecin.”
* **starosta of Legionowo County (starosta legionowski)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11717579 2006–2015 — “W latach 2006–2015 starosta legionowski”
* **Chairman of the Kraków City Council**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Chief of the Cabinet of the President of the Republic of Poland (Szef Gabinetu Prezydenta RP)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Councillor of the Sejmik of the Podlaskie Voivodeship**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Deputy Marshal of Kuyavian-Pomeranian Voivodeship (wicemarszałek województwa kujawsko-pomorskiego)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Deputy Mayor of Chełm**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Deputy Voivode of West Pomeranian Voivodeship (wicewojewoda zachodniopomorski)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Deputy Voivode of Łódź Voivodeship (wicewojewoda łódzki)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Head of the International Policy Bureau, Chancellery of the President of the Republic of Poland**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Leader of Poland 2050**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Member of the Kalisz City Council**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Member of the Regional Assembly of West Pomeranian Voivodeship (radny Sejmiku Województwa Zachodniopomorskiego)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Member of the Sejmik of the Łódź Voivodeship (radny Sejmiku Województwa Łódzkiego)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Member of the Wrocław County Council**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Pełnomocnik Rządu do spraw Małych i Średnich Przedsiębiorstw (Government Plenipotentiary for Small and Medium Enterprises, Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **President (mayor) of Piła**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Secretary of State in the Chancellery of the President of the Republic of Poland (sekretarz stanu w Kancelarii Prezydenta RP)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Secretary of State in the Chancellery of the Prime Minister of Poland**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Secretary of State in the Chancellery of the Prime Minister of Poland (sekretarz stanu w Kancelarii Prezesa Rady Ministrów)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Secretary of State in the Ministry of Culture and National Heritage (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Secretary of State in the Ministry of Family, Labour and Social Policy (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Secretary of State in the Ministry of Foreign Affairs (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Secretary of State in the Ministry of Sport and Tourism (sekretarz stanu w Ministerstwie Sportu i Turystyki), Poland**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Secretary of State in the Ministry of the Environment of Poland (sekretarz stanu w Ministerstwie Środowiska)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Undersecretary of State in the Ministry of Agriculture and Rural Development (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Undersecretary of State in the Ministry of Foreign Affairs (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Undersecretary of State in the Ministry of Health (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Undersecretary of State in the Ministry of State Assets (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Vice-Marshal of the Podlaskie Voivodeship**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **Voivode of Bydgoszcz Voivodeship (wojewoda bydgoski)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **członek zarządu województwa lubuskiego (member of the executive board of Lubusz Voivodeship)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **member of the Warsaw City Council**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **member of the Łódź City Council**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **member of the Łódź Voivodeship Sejmik**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **przewodniczący Sejmiku Województwa Śląskiego (Chairman of the Sejmik of the Silesian Voivodeship)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **radny Sejmiku Województwa Mazowieckiego (councillor of the Masovian Regional Assembly)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **radny Sejmiku Województwa Mazowieckiego (member of the Masovian Regional Assembly)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **radny dzielnicy Żoliborz (Warsaw district councillor)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **sekretarz stanu w Ministerstwie Edukacji i Nauki**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **sekretarz stanu w Ministerstwie Nauki i Szkolnictwa Wyższego (Secretary of State in the Ministry of Science and Higher Education, Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **starosta of Pabianice County**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **starosta powiatu kłobuckiego**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **wicemarszałek województwa lubuskiego (Vice-Marshal of Lubusz Voivodeship)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **wiceprezydent Poznania (deputy mayor of Poznań)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **wicestarosta powiatu starogardzkiego (deputy starost of Starogard County)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **wójt gminy Biłgoraj**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **wójt gminy Dzierżoniów**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **wójt gminy Kotla**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **wójt gminy Pruszcz Gdański**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **wójt of gmina Płużnica**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
* **zastępczyni prezydenta Wałbrzycha (deputy mayor of Wałbrzych)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`

## `ambiguous` (6)

Candidates found and no unique two-signal match. A human picks, or the name is too coarse to place at all.

* **Deputy Marshal of the Sejm**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11694886 2023-11-13 — “On November 13, 2023, she was elected Deputy Marshal of the Sejm of the 10th term.”
  * candidate [-C] Q5261044 Deputy Marshal of the Sejm of the Republic of Poland
* **Minister for Civil Society (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q112653327 2023-12-13–2024-10-16 — “war vom 13. Dezember 2023 bis 16. Oktober 2024 Ministerin für die Zivilgesellschaft im Kabinett Tusk III”
  * candidate [L-] Q6865761 Minister for Civil Society
* **Minister of Education and Science (Poland)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q100592001 2023-11-27–2023-12-13 — “Am 27. November 2023 wurde er vom Präsidenten der Republik Polen zum Minister für Bildung und Wissenschaft im III. Kabinett von Mateusz Morawiecki ernannt.”
  * candidate [L-] Q25478039 Minister of Education and Science
  * candidate [L-] Q35959997 Minister of Education and Science
* **Presidente del Congreso de la República de Guatemala**  ·  `es_Diputados_de_Guatemala`
  * Q136708231 2026-01 — “Fue electo como presidente del Congreso de la República de Guatemala, cargo que asumió en enero de 2026”
  * candidate [-C] Q6594745 President of the Congress of the Republic of Guatemala
* **minister-member of the Council of Ministers of Poland (minister without portfolio)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * Q11717579 2023-12-13 — “Następnego dnia został przez prezydenta RP Andrzeja Dudę powołany na to stanowisko.”
  * candidate [L-] Q1937160 Minister without Portfolio
  * candidate [L-] Q15733044 Minister without portfolio
* **Voivode of West Pomeranian Voivodeship (wojewoda zachodniopomorski)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [-C] Q60979102 Voivodes of West Pomeranian Voivodeship

## `no-polity` (4)

An item matched and was **refused** because it names no polity it governs — `recipes/position_items.md` calls that a defect, and writing a specific mayoralty onto a generic administrative rank is the generic-occupation trap. Either the item wants a `P1001` or a real office wants creating.

* **President of the Congress of the Republic of Guatemala**  ·  `en_Members_of_the_Congress_of_Guatemal`, `es_Diputados_de_Guatemala`
  * Q124318743 2024-01-19–2026-01-14 — “He was elected President of the Congress of the Republic of Guatemala on 19 January 2024”
  * candidate [LC] Q6594745 President of the Congress of the Republic of Guatemala
* **Chairman of New Hope (Nowa Nadzieja)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q19600733 New Hope
  * candidate [L-] Q17738 Star Wars: Episode IV – A New Hope
* **Deputy Marshal of the Senate of the Republic of Poland (wicemarszałek Senatu)**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q5261047 Deputy Marshal of the Senate of the Republic of Poland
* **Mayor (wójt) of Świlcza**  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [--] Q37497457 Wojt
  * candidate [L-] Q30185 mayor

## `placed` (14)

Matched on two signals; the run already wrote the P39.

* **Chief of the Chancellery of the Prime Minister (Szef Kancelarii Prezesa Rady Ministrów)** → Q107919931  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q107919931 Chief of the Chancellery of the Prime Minister of Poland
* **Marshal of Lublin Voivodeship** → Q140458485  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q140458485 Marshal of Lublin Voivodeship
* **Marshal of Lubusz Voivodeship** → Q140458549  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q140458549 Marshal of Lubusz Voivodeship
* **Minister of Agriculture and Rural Development (Poland)** → Q107919710  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [L-] Q15731462 Minister of Agriculture and Rural Development
  * candidate [L-] Q109661491 Minister of Agriculture and Rural Development
* **Minister of Development and Technology (Poland)** → Q101246734  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q101246734 Minister of Development and Technology
* **Minister of Digital Affairs (Poland)** → Q107919830  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q107919830 Minister of Digital Affairs
  * candidate [L-] Q113630396 Minister of Digital Affairs
* **Minister of Finance (Poland)** → Q11781525  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [L-] Q7614320 finance minister
  * candidate [L-] Q2367542 Minister of Finance
* **Minister of Health of Poland** → Q57775575  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q57775575 Minister of Health
* **Prezydent Olsztyna (Mayor of Olsztyn)** → Q110680377  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q110680377 mayor of Olsztyn
* **Senator of Poland (VIII term)** → Q81747225  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q81747225 Member of the Senate of the Republic of Poland
* **Senator of Poland (X term)** → Q81747225  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q81747225 Member of the Senate of the Republic of Poland
  * candidate [--] Q2629100 X-Terminator
* **Senator of Poland (senator Rzeczypospolitej Polskiej)** → Q81747225  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q81747225 Member of the Senate of the Republic of Poland
* **Senator of the Republic of Poland (VII term)** → Q81747225  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q81747225 Member of the Senate of the Republic of Poland
* **Senator of the Republic of Poland (member of the Senate of Poland)** → Q81747225  ·  `pl_Posłowie_na_Sejm_Rzeczypospolitej_P`
  * candidate [LC] Q81747225 Member of the Senate of the Republic of Poland

