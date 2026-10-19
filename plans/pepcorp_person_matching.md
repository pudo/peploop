---
description: Person matching for pepcorp seats whose person the body's article names but does not link — 41 hand-judged cases from the EU + CH dry run, the plausibility standard the candidate's own Wikipedia page must meet, and the expected yield and error rate.
date: 2026-10-18
tags: [pepcorp, person-resolution, matching, seats, standard]
---

# pepcorp: matching unlinked seat holders

Builds on `plans/pepcorp_next.md` §2. The user's requirement (2026-10-18):
search by name fuzzily, then hold the candidate's Wikipedia page to a strict
standard — at least the industry or domain, ideally the institution.

## Where the seats are

6,584 `person_unlinked` seats on the ledger (de and nl included); 5,020 would
pass the date rules if the person were linked (3,900 without de/nl/no/zm). A
random 200 of the EU+CH ones, after the fuzzy search:

| what the search finds | seats |
|---|---|
| no human item fits the name | 101 (50 %) |
| only items without a page in the country's languages or English | 53 (27 %) |
| at least one candidate with a page | 46 (23 %) |

The page-less items are mostly bare author records (ORCID "researcher"), but
a few name the body in their description ("director Federal Office for the
Environment in 2020", "Chairman of the Board - Vattenfall AB"). By the
standard below they are not matched (see open questions).

## Search

`persons.candidates`: Wikidata's full-text search (`haswbstatement:P31=Q5`,
folds accents, all languages' labels and aliases) plus each country
Wikipedia's own search, filtered by `persons.name_fits`:

- names folded to Latin script without accents (`normality.ascii_text`), titles
  and degrees dropped (`rules.norm`), particles (von, de, van …) ignored;
- order free (family name first in Hungarian), a middle name or second
  surname on one side only allowed, initials fit their name, one letter apart
  in a token of 5+ letters (two in 8+) for transliteration and inflection;
- at least two whole tokens agree: a lone surname or initials never fit;
- typed `P31 Q5`, a page in the country's languages or English, a lifetime
  that holds the seat (21+ at its start, alive at its start, not over 95 if
  current); more than `MAX_CANDIDATES` paged namesakes is a crowd, left alone.

## The 41 cases

Drawn at random per country (two for the large ones) among seats with at
least one paged candidate; each candidate's page and item read by hand, then
the model check run on the same material. Hand and model verdicts agree on
all 41 (my first hand verdict on Fiorini was wrong: her page does say
"Dal maggio 2026 è Consigliere di Eni").

| cc | body (kind) | seat | name | cands | verdict | evidence |
|---|---|---|---|---|---|---|
| at | Agentur für Luft- und Raumfahrt (inst.) | head | Harald Posch | 1 | reject | actor and theatre director; the seat-holder died 2015 |
| at | OÖ Gesundheitsholding (ent.) | MD | Karl Lehner | 2 | reject | opera singer; painter died 2006 (date filter) |
| be | NICC (inst.) | head | Jan De Kinder | 1 | none | baroque sculptor, dropped by lifetime |
| be | TV5 Monde (ent.) | chair | Kim Younes Charbit | 1 | **institution** | page: PDG of TV5 Monde since Oct 2024, links body |
| bg | ГДБОП (inst.) | head | Кирил Георгиев | 6 | reject | poet, chess GM, mayor born 1982 (conflict) … |
| ch | Bundesamt für Kultur (inst.) | head | Jean-Frédéric Jauslin | 1 | **institution** | "direttore dell'Ufficio federale della cultura" 2005–2013 |
| ch | Eidg. Finanzverwaltung (inst.) | head | Peter Siegenthaler | 2 | reject | cantonal SP politician who "worked in public administration": the trap a loose domain tier falls into |
| cy | Civil Defence (inst.) | head | Maria Papa | 1 | reject | Italian physicist |
| cz | Drážní inspekce (inst.) | head | Jaroslav Dvořák | 6 | reject | neurologist-MP, historian-mayor, footballer … |
| cz | ČD Cargo (ent.) | head | Ivan Bednárik | 1 | **institution** | "předsedou představenstva ČD Cargo" 2014–2020 |
| dk | Det Danske Filminstitut (inst.) | head | Tine Fischer | 2 | **institution** | "direktør for Det Danske Filminstitut"; Fischer-Tiné (order-free fit) rejected |
| dk | Trafikstyrelsen (inst.) | head | Nanna Møller | 1 | reject | film editor |
| ee | Mahtra Talurahvamuuseum (inst.) | head | Jaanus Plaat | 1 | **institution** | "Mahtra Talurahvamuuseumi tegevjuht" |
| es | Instituto para la Transición Justa (inst.) | chair | Sara Aagesen Muñoz | 1 | **domain** | Secretary of State for Energy 2020–24; passage says "(Secretaria de Estado)" |
| es | Puertos del Estado (inst.) | head | Gustavo Santana Hernández | 1 | reject | Michael Jackson impersonator "Gustavo Hernández Santana" (order-free fit) |
| fi | Sitra (inst.) | chair | Mika Lintilä | 1 | **institution** | page names Sitra; minister, Centre MP as in the passage |
| fi | Sitra (inst.) | member | Peter Östman | 1 | **domain** | KD MP, as the passage's "(kd.)"; Sitra's council is MPs |
| fr | Canal France International (ent.) | head | Marc Fonbaustier | 1 | **institution** | deputy MD of CFI (as Agence de Coopération Médias) |
| fr | Grand port maritime de Bordeaux (ent.) | head | Jean-Frédéric Laurent | 1 | reject | a pseudonym of Alain de Benoist |
| gr | ΚΠΙΣΝ (inst.) | chair | Stathis Kalyvas | 1 | **institution** | "πρόεδρος του διοικητικού συμβουλίου του Κέντρου Πολιτισμού…" Dec 2023 |
| hr | Institut Ruđer Bošković (inst.) | head | David Matthew Smith | 1 | none | sculptor died 1965 (lifetime) |
| hu | Magyar Fejlesztési Bank (ent.) | head | Baranyay László | 1 | reject | pianist |
| hu | NEAK (inst.) | head | Kiss Zsolt | 6 | crowd | curler, footballers, actor … |
| ie | Coimisiún na Meán (inst.) | head | Jeremy Godfrey | 1 | reject | music producer, once at BBC Radio 1: media ≠ media regulation |
| it | Eni (ent.) | member | Benedetta Fiorini | 1 | **institution** | "Dal maggio 2026 è Consigliere di Eni" |
| it | Agenzia delle Entrate (inst.) | head | Raffaele Ferrara | 3 | reject | cyclist, carabiniere |
| lt | Turto bankas (ent.) | head | Mindaugas Sinkevičius | 2 | reject | the prime minister: mayor through the seat's years (conflict) |
| lt | Ignalina NPP (ent.) | chair | Romas Švedas | 1 | **domain** | "energetikos viceministras", as the passage says |
| lu | CGDIS (inst.) | head | Paul Schroeder | 6 | reject | philatelist; the rest dead |
| lv | Pasažieru vilciens (ent.) | member | Aigars Štokenbergs | 1 | **institution** | appointed PV board member 2012, links body |
| lv | Valsts robežsardze (inst.) | head | Guntis Pujāts | 1 | reject | ice hockey player |
| mt | Malta Enterprise (inst.) | head | George Gregory | 6 | none | all dead centuries ago |
| pl | ZUS (inst.) | member | Joanna Stachura | 1 | reject | architect "Ewa Joanna Stachura" |
| pl | Polska Agencja Kosmiczna (inst.) | head | Marek Banaszkiewicz | 1 | none | footballer died 2000 |
| pt | Torre do Tombo (inst.) | head | Paulo Batista | 6 | crowd | Brazilian athletes |
| ro | BCU Iași (inst.) | head | Gheorghe Teodorescu | 5 | reject | painter; the rest dead |
| ro | ANCPI (inst.) | head | Mihai Busuioc | 2 | **institution** | registrar, then leading posts at ANCPI; later Court of Accounts |
| se | Högskolan i Gävle (inst.) | head | Leif Svensson | 3 | reject | passage says "professor i matematik": hockey player, civil servant (conflict) |
| se | Kungliga Konsthögskolan (inst.) | head | Peter Geschwind | 1 | **institution** | "acting rector from 2016 to 2017" |
| si | SOVA (inst.) | head | Zoran Klemenčič | 1 | reject | cyclist |
| sk | SHMÚ (inst.) | head | Martin Benko | 2 | reject | footballer |

15 matched (11 institution, 4 domain), 26 not; no accepted match wrong on
reading. Every domain-tier accept rests on a detail the passage itself gives
(a party, a former office) or on the body's own field at its level.

## The standard

The candidate's own Wikipedia page is the evidence; the item's facts only
support it. Per candidate, the check answers a tier and same-person:

1. **institution** — the page names the body (any name, abbreviation,
   former or foreign name) or links it, tying the candidate to it (worked,
   led, sat on its board, appointed, ex officio). The seat itself need not be
   on the page. → accept.
2. **domain** — the page does not name the body but places the career in the
   body's own field at a fitting level (energy policy for an energy company,
   curating for a museum, the sector's ministry for an agency, parliament for
   a council of MPs), or confirms a detail the passage gives (party, former
   office, profession). Generic "politician", "civil servant", "lawyer",
   "businessperson", "academic" is no field; working in an industry as an
   artist or athlete is not its management. → accept only when no other
   candidate passes and the seat has at most three paged candidates.
3. **none** — a career elsewhere, or nothing related. → reject.
4. **conflict** — dead, too young, another country for a national body, a
   full-time post elsewhere through a head's tenure, a passage detail the page
   contradicts. → reject.

Also: no page, no match (page-less items are out); a detailed career page
silent on a prominent seat counts against a domain match; one institution
candidate wins over domain ones, two at the same best tier are namesakes
and the seat stays out. A matched seat then goes through every seat rule
(holder_dead, head_other, dates); the statement keeps the body's article as
its reference, the match being an inference.

## Expected yield and error

23 % of unlinked seats have a paged candidate, and about a third of those
match (15/41 here; the sample was drawn among seats with candidates): about
8 % of the eligible unlinked seats, ~300 on EU+CH, ~70 on Germany. Far below
the earlier "unique item by name" ceiling (~1,500), because half the names
have no item and a quarter only page-less ones. Error: 0/15 on this sample;
the risk sits in the domain tier (4 of 15), where a namesake with a career
in the same field would pass. Cost: ~$0.005 per candidate checked.

## Open questions

- Page-less items whose description or `P108`/`P39` names the body (seen:
  FOEN's director, Vattenfall's chair): the user ruled 2026-10-19 that item
  data counts as evidence. Now the `item` tier, equal to `institution`,
  decided in code without a call (`match.item_ties`); Switzerland went from
  10 to 47 matched seats.
- People without items (half the seats) stay residue: pepcorp creates no
  people.

## Result of the build (2026-10-18)

`persons.py`, `match.py`, `prompts/match_person.md`, wired into `run.py`
after the link check; fixtures in `check_persons.py`. All 26 countries
re-planned from cached decisions (nothing sent):

| cc | written | link | anchor | matched | still unlinked |
|---|---|---|---|---|---|
| at | 117 | 106 | 2 | 9 | 257 |
| be | 99 | 88 | 1 | 10 | 159 |
| bg | 57 | 49 | 2 | 6 | 66 |
| ch | 97 | 88 | 0 | 9 | 212 |
| cy | 4 | 3 | 0 | 1 | 18 |
| cz | 103 | 96 | 0 | 7 | 170 |
| dk | 64 | 58 | 0 | 6 | 113 |
| ee | 74 | 71 | 1 | 2 | 79 |
| es | 135 | 95 | 11 | 29 | 310 |
| fi | 178 | 153 | 0 | 25 | 170 |
| fr | 325 | 302 | 3 | 20 | 444 |
| gr | 12 | 5 | 0 | 7 | 45 |
| hr | 7 | 7 | 0 | 0 | 46 |
| hu | 60 | 55 | 0 | 5 | 113 |
| ie | 10 | 10 | 0 | 0 | 29 |
| it | 103 | 92 | 0 | 11 | 247 |
| lt | 65 | 63 | 0 | 2 | 113 |
| lu | 32 | 31 | 1 | 0 | 83 |
| lv | 26 | 24 | 0 | 2 | 104 |
| mt | 5 | 5 | 0 | 0 | 23 |
| pl | 292 | 280 | 0 | 12 | 381 |
| pt | 14 | 11 | 0 | 3 | 60 |
| ro | 43 | 32 | 1 | 10 | 196 |
| se | 530 | 501 | 8 | 21 | 214 |
| si | 13 | 12 | 0 | 1 | 22 |
| sk | 4 | 3 | 0 | 1 | 54 |
| all | 2,469 | 2,240 | 30 | 199 | 3,728 |

Seven more matches were already on Wikidata as the same statement
(`plan:exists`), an independent confirmation. Yield is ~5 % of the unlinked
seats, below the 8 % estimate: the lifetime filter and the crowd limit take
more than the sample showed. Finland is high (Sitra's council of MPs, party
tags confirmed); Croatia, Ireland, Malta, Luxembourg nothing.

Precision: all 32 matched seats of at, it, pl read against the pages, no
error; ~80 more read across the other countries. One wrong match found:
ITL Eisenbahngesellschaft's CEO "Christian Kern" matched on the domain tier
(railways) to the former Austrian chancellor; with it, Fransaer as interim
head of LIST (a Belgian, plausible but unproven). Fixed by rule: a
domain-tier match must hold the country's citizenship where the item
states any (institution tier unaffected). Least certain left: Werner Gruber
on the NHM board, Antonis Stylianou chairing the Cyprus Ports Authority,
both domain tier. Model spend: $5.01 for 1,138 checks (calibration included).
