# Task: resolve conflicting gender (P21) data for PEP persons

Input: ~170 Wikidata QIDs where the OpenSanctions entity carries more than one
`gender` value (list in the appendix). Goal: for each, decide whether Wikidata
itself holds a false P21 statement, and if so prepare a reviewed edit — not
bulk-fix everything blindly. Some entries are correct as-is (genuinely
multiple gender identities); some conflicts don't even exist on Wikidata.

## Key insight (from spot checks, 2026-08-04)

OS merges several sources per person, so **"OS shows two genders" ≠ "Wikidata
has two P21 statements"**. Four probes:

| QID | OS values | Wikidata P21 actual | Case |
|---|---|---|---|
| Q108686518 Stenyakina | female, male | **one** stmt: female (ref: P887 "based on heuristic"!) | conflict is OS-side; WD fine |
| Q115580983 Farivar | female, other | **one** stmt: female, unreferenced | WD possibly *missing* non-binary value |
| Q15025 Audrey Tang | female, other | **two** stmts: non-binary + trans woman, both well-referenced | legit; no edit |
| Q98258587 Didier Robin | female, male | **two** stmts: female (ref P248) + male (unref) | the real fix case |

So step one is always a live fetch of the item's actual P21 claims with ranks
and references — triage before any article reading.

## Triage buckets

* **A — WD has one P21 value.** The OS conflict comes from merging another
  source. No Wikidata contradiction to fix. Sub-cases:
  * A1: WD value looks right (matches article evidence) → no WD edit; the
    conflicting value is an OS/source problem — log for the OS side.
  * A2: WD value looks wrong → propose fix (add correct value, deprecate the
    wrong statement).
  * A3: WD value incomplete (e.g. publicly non-binary person with plain
    `female`) → possible *additive* edit, only with a solid public
    self-identification source.
* **B — WD has ≥2 P21 values, ranks undifferentiated.** The core cleanup
  target. Typical shape: one referenced human-curated value + one unreferenced
  bot/heuristic value. Propose: deprecate the false one (rank → deprecated,
  qualifier P2241 = Q41755623 "incorrect value"), keep the correct one at
  normal rank.
* **C — WD has ≥2 values that are all intentional** (trans/non-binary
  identities, e.g. Q15025) → explicitly no-op; mark as resolved-correct.

Statements whose ranks are *already* differentiated (deprecated/preferred set)
are half-done — verify and skip.

## Evidence, per undecided case

1. **Statement metadata first** (cheap, already fetched): references — an
   unreferenced or `P887 based on heuristic` or `P143 imported from ...` value
   loses against a value referenced to a curated source (P248); statement age
   / origin if needed (revision history).
2. **Wikipedia article** (the LLM-reading step): pronouns in running text,
   gendered categories ("Women members of …", "Женщины-политики …"),
   explicit statements of identity. Prefer the person's native-language
   article — many of these people (RU, VN, ZH, IN, African francophone) have
   thin English articles or none. `fetch_article.py` should take QID →
   resolve sitelinks → fetch chosen language versions as plaintext.
3. **Names are weak evidence** — that's exactly the heuristic that produced
   bad data (see Q108686518's P887 ref). Use only as a tiebreak flag, never
   as the sole basis for an edit.
4. No article, no source, no clarity → **no edit**; log as unresolved.

## Edit policy

* Wrong value in a multi-value item → **deprecate, don't delete**: rank →
  `deprecated` + P2241 (reason for deprecated rank) = Q41755623 ("incorrect
  value"). Keeps history and blocks re-import by bots.
* Exception: obvious vandalism or an unreferenced bot artifact on an item
  that never had another value may be deleted outright — decide per case in
  review.
* Additive edits (A2/A3) need a citable public source (P854 + P813, or P248);
  self-identification only — never infer gender identity.
* Sensitivity: these are living people; for trans/non-binary subjects,
  misgendering edits do real harm. Anything not clear-cut goes to the
  unresolved pile, not into the batch.
* All edits reviewed by a human before running; apply via `wikibase-cli`
  (`wd update-claim-rank <guid> deprecated`, `wd add-qualifier`, …) so the
  batch lands as an edit group and is mass-revertable.

## Pipeline / scripts to build

1. `scripts/fetch_genders.py` — for every input QID: live P21 statements
   (GUID, value, rank, qualifiers, references), label, sitelinks. Emit one
   JSON per item (`data/genders/{qid}.json`) + a triage table
   (`data/genders/triage.csv`: qid, name, wd_values, ranks, refs summary,
   bucket guess).
2. `scripts/fetch_article.py` — QID + language preference → Wikipedia
   article plaintext (`data/articles/{qid}.{lang}.txt`). Shared with future
   tasks (positions!). Test plaintext extract vs HTML→markdown.
3. LLM review pass (me, in-session, batch by bucket): read triage row +
   article evidence → verdict + proposed edit + confidence, into
   `data/genders/verdicts.jsonl`.
4. `scripts/render_edit_plan.py` — verdicts → human-readable review doc +
   executable `wd`-command list.
5. Human review → execute → re-fetch and verify.

## Status

- [x] Spot checks done (4 QIDs, see table)
- [ ] fetch_genders.py + triage of all ~170
- [ ] article fetcher
- [ ] LLM review pass
- [ ] edit plan + review + execution

## Appendix: input list (OS entities with >1 gender value)

```
[https://opensanctions.org/entities/Q100979602]: 'Mpho Gift Modise' -> ['female', 'male']
[https://opensanctions.org/entities/Q104124235]: 'Eva Burešová' -> ['female', 'male']
[https://opensanctions.org/entities/Q104124266]: 'Libuše Vévodová' -> ['female', 'male']
[https://opensanctions.org/entities/Q104803006]: 'Lauren McDonald' -> ['female', 'male']
[https://opensanctions.org/entities/Q105107031]: 'K C Rosakutty Teacher' -> ['female', 'male']
[https://opensanctions.org/entities/Q105153839]: 'George Akosa' -> ['female', 'male']
[https://opensanctions.org/entities/Q105301361]: 'ERIKA SANTOS SILVA' -> ['female', 'other']
[https://opensanctions.org/entities/Q106564661]: 'Raquel Bonilla Herrera' -> ['female', 'male']
[https://opensanctions.org/entities/Q106621543]: 'Svetlana Victorovna Razvorotneva' -> ['female', 'male']
[https://opensanctions.org/entities/Q106688671]: 'Elysium Bokumuamua Maposo' -> ['female', 'male']
[https://opensanctions.org/entities/Q106786463]: 'Kelly Kortum' -> ['female', 'male']
[https://opensanctions.org/entities/Q10798991]: 'Nguyễn Cao Sơn' -> ['female', 'male']
[https://opensanctions.org/entities/Q10825772]: 'Thái Thị An Chung' -> ['female', 'male']
[https://opensanctions.org/entities/Q108370229]: 'SYMMY LARRAT BRITO DE CARVALHO' -> ['female', 'other']
[https://opensanctions.org/entities/Q108686518]: 'Ekaterina Petrovna Stenyakina' -> ['female', 'male']
[https://opensanctions.org/entities/Q108864931]: 'Larisa Nikolaevna Buranova' -> ['female', 'male']
[https://opensanctions.org/entities/Q108878862]: 'Olga Nikolaevna Anufrieva' -> ['female', 'male']
[https://opensanctions.org/entities/Q108894635]: 'Olga Nikolaevna Amelchenkova' -> ['female', 'male']
[https://opensanctions.org/entities/Q109484601]: 'Barabanshchikova Valentina Vladimirovna' -> ['female', 'male']
[https://opensanctions.org/entities/Q109495767]: 'Kuizheva Saida Kazbekovna' -> ['female', 'male']
[https://opensanctions.org/entities/Q110557130]: 'Eunice Pontes' -> ['female', 'male']
[https://opensanctions.org/entities/Q111149808]: 'Halima Hassan Tukur' -> ['female', 'male']
[https://opensanctions.org/entities/Q111355884]: 'HAMAN PAUL' -> ['female', 'male']
[https://opensanctions.org/entities/Q111355885]: 'MAANDE Paul' -> ['female', 'male']
[https://opensanctions.org/entities/Q111355887]: 'Mme BISSECK Paulette' -> ['female', 'male']
[https://opensanctions.org/entities/Q111355888]: 'Bebnone Payounni' -> ['female', 'male']
[https://opensanctions.org/entities/Q111355905]: 'NAAH ONDOUA Sylvestre' -> ['female', 'male']
[https://opensanctions.org/entities/Q111481655]: 'GERMANA FIGUEROA CASAS' -> ['female', 'male']
[https://opensanctions.org/entities/Q111525351]: 'Leticia García Sánchez' -> ['female', 'male']
[https://opensanctions.org/entities/Q11180963]: 'Long Guoying' -> ['female', 'male']
[https://opensanctions.org/entities/Q112133372]: 'Adoracion Salas Chonco' -> ['female', 'male']
[https://opensanctions.org/entities/Q112300339]: 'Keturah Herron' -> ['female', 'other']
[https://opensanctions.org/entities/Q112613522]: 'Rajendra Laxmi Gaire' -> ['female', 'male']
[https://opensanctions.org/entities/Q114716797]: 'Gulnara Baatyrova' -> ['female', 'male']
[https://opensanctions.org/entities/Q115580983]: 'Darya Farivar' -> ['female', 'other']
[https://opensanctions.org/entities/Q115857022]: 'Santosh Pariyar' -> ['female', 'male']
[https://opensanctions.org/entities/Q116059731]: 'Lorena Austin' -> ['female', 'other']
[https://opensanctions.org/entities/Q116144937]: 'Brion Curran' -> ['female', 'other']
[https://opensanctions.org/entities/Q116203609]: 'Dalton Banks' -> ['female', 'male']
[https://opensanctions.org/entities/Q116416964]: 'Joël Nguiebe' -> ['female', 'male']
[https://opensanctions.org/entities/Q116875328]: 'Phúc Bình Niê Kdăm' -> ['female', 'male']
[https://opensanctions.org/entities/Q117321689]: 'Skroznikova Anna Valerievna' -> ['female', 'male']
[https://opensanctions.org/entities/Q117338224]: 'Monique Paccolat' -> ['female', 'male']
[https://opensanctions.org/entities/Q120011534]: 'Marta Díez Napal' -> ['female', 'male']
[https://opensanctions.org/entities/Q120146877]: 'Miriam van Meerten-Kok' -> ['female', 'male']
[https://opensanctions.org/entities/Q12290659]: 'Petya Raeva' -> ['female', 'male']
[https://opensanctions.org/entities/Q123485381]: 'Vroni Thalmann-Bieri' -> ['female', 'male']
[https://opensanctions.org/entities/Q124321989]: 'Ambureen Rana' -> ['female', 'other']
[https://opensanctions.org/entities/Q124370561]: 'Ibrahima Bangoura' -> ['female', 'male']
[https://opensanctions.org/entities/Q124607177]: 'Sam Montaño' -> ['female', 'other']
[https://opensanctions.org/entities/Q125687354]: 'Ortésia Cabrera Fuster' -> ['female', 'other']
[https://opensanctions.org/entities/Q126364974]: 'Mitali Bag' -> ['female', 'male']
[https://opensanctions.org/entities/Q126365214]: 'Byreddy Shabari' -> ['female', 'male']
[https://opensanctions.org/entities/Q126365264]: 'Bijuli Kalita Medhi' -> ['female', 'male']
[https://opensanctions.org/entities/Q126365308]: 'Shobhanaben Mahendrasinh Baraiya' -> ['female', 'male']
[https://opensanctions.org/entities/Q12646955]: 'Adam Blaškevič' -> ['female', 'male']
[https://opensanctions.org/entities/Q126617228]: 'Loumy Bourghol' -> ['female', 'male']
[https://opensanctions.org/entities/Q12709122]: 'Shahanim Mohamad Yusoff' -> ['female', 'male']
[https://opensanctions.org/entities/Q127268816]: "Sarah T'Joens" -> ['female', 'male']
[https://opensanctions.org/entities/Q127559959]: 'Alissandra Murray' -> ['female', 'other']
[https://opensanctions.org/entities/Q128304750]: 'Caroline Desalle' -> ['female', 'male']
[https://opensanctions.org/entities/Q131141667]: 'Ikaika Olds' -> ['female', 'male']
[https://opensanctions.org/entities/Q131141673]: 'Ikaika Hussey' -> ['female', 'male']
[https://opensanctions.org/entities/Q133302261]: 'Ludupova Evgenia Yurievna' -> ['female', 'male']
[https://opensanctions.org/entities/Q134297356]: 'Jacqueline Sagna' -> ['female', 'male']
[https://opensanctions.org/entities/Q134973262]: 'Marianna Anaya' -> ['female', 'other']
[https://opensanctions.org/entities/Q134984049]: 'Mike Berg' -> ['female', 'male']
[https://opensanctions.org/entities/Q135088632]: 'Billie Butler' -> ['female', 'other']
[https://opensanctions.org/entities/Q135234022]: 'Lisa Schubert' -> ['female', 'other']
[https://opensanctions.org/entities/Q135675760]: 'Lushious Massacr' -> ['male', 'other']
[https://opensanctions.org/entities/Q135687526]: 'Emily Carris-Duncan' -> ['female', 'other']
[https://opensanctions.org/entities/Q135978298]: 'Rolf Hegetschweiler' -> ['female', 'male']
[https://opensanctions.org/entities/Q136324588]: 'NDACK THIAM' -> ['female', 'male']
[https://opensanctions.org/entities/Q137599638]: 'Tracy Sharp' -> ['female', 'male']
[https://opensanctions.org/entities/Q137754206]: 'Cholpon Ecenamanova' -> ['female', 'male']
[https://opensanctions.org/entities/Q137768864]: 'Carrie Briggs' -> ['female', 'male']
[https://opensanctions.org/entities/Q138680208]: 'Shoshana Strook' -> ['female', 'male']
[https://opensanctions.org/entities/Q138750966]: 'Dana Henry' -> ['female', 'male']
[https://opensanctions.org/entities/Q138758818]: 'Olivier Gilbert' -> ['female', 'male']
[https://opensanctions.org/entities/Q138759535]: 'Philippe Gregoire' -> ['female', 'male']
[https://opensanctions.org/entities/Q14134632]: 'Trenzano Rubio, Marta' -> ['female', 'male']
[https://opensanctions.org/entities/Q1491004]: 'Sara Duterte' -> ['female', 'male']
[https://opensanctions.org/entities/Q15025]: 'Audrey Tang' -> ['female', 'other']
[https://opensanctions.org/entities/Q152318]: 'Svetlana Evgenievna Savitskaya' -> ['female', 'male']
[https://opensanctions.org/entities/Q16336443]: 'Guan Min' -> ['female', 'male']
[https://opensanctions.org/entities/Q16728108]: 'Mary Coble' -> ['female', 'other']
[https://opensanctions.org/entities/Q16744501]: 'Mamosoeu Makgate' -> ['female', 'male']
[https://opensanctions.org/entities/Q16868356]: 'Nancy E. Rice' -> ['female', 'male']
[https://opensanctions.org/entities/Q16904755]: 'Zhou Sumin' -> ['female', 'male']
[https://opensanctions.org/entities/Q16906538]: 'Mou Shuijuan' -> ['female', 'male']
[https://opensanctions.org/entities/Q16906731]: 'Su Guozhang' -> ['female', 'male']
[https://opensanctions.org/entities/Q16921081]: 'Cui Fuhua' -> ['female', 'male']
[https://opensanctions.org/entities/Q17107263]: 'Jan Ketil Simonsen' -> ['female', 'male']
[https://opensanctions.org/entities/Q19542816]: 'Louis Marandi' -> ['female', 'male']
[https://opensanctions.org/entities/Q19749110]: 'Sri Ugrasena' -> ['female', 'male']
[https://opensanctions.org/entities/Q20645666]: 'Alexei Graf von Bismarck-Schönhausen' -> ['female', 'male']
[https://opensanctions.org/entities/Q21099348]: 'Amra Kvarandzia' -> ['female', 'male']
[https://opensanctions.org/entities/Q22006757]: 'Kelly McCauley' -> ['female', 'male']
[https://opensanctions.org/entities/Q22279740]: 'Sudama Prasad' -> ['female', 'male']
[https://opensanctions.org/entities/Q24951660]: 'Luc René Bell' -> ['female', 'male']
[https://opensanctions.org/entities/Q28420154]: 'Shawn Thierry' -> ['female', 'male']
[https://opensanctions.org/entities/Q30303013]: 'Lakhan Singh' -> ['female', 'male']
[https://opensanctions.org/entities/Q30921480]: 'Đỗ Đức Hồng Hà' -> ['female', 'male']
[https://opensanctions.org/entities/Q34791131]: 'Ghazala Saad Rafique' -> ['female', 'male']
[https://opensanctions.org/entities/Q35539642]: 'Olufunke Adedoyin' -> ['female', 'male']
[https://opensanctions.org/entities/Q37861267]: 'Marthese Portelli' -> ['female', 'male']
[https://opensanctions.org/entities/Q4062385]: 'Olga Nikolaevna Alimova' -> ['female', 'male']
[https://opensanctions.org/entities/Q4358028]: 'Jeremy Cronin' -> ['female', 'male']
[https://opensanctions.org/entities/Q4374973]: 'Potupchik Kristina Andreevna' -> ['female', 'male']
[https://opensanctions.org/entities/Q45025253]: 'Fawzia Peer' -> ['female', 'male']
[https://opensanctions.org/entities/Q4739200]: 'Amal Pepple' -> ['female', 'male']
[https://opensanctions.org/entities/Q47500614]: 'Anita Kulik' -> ['female', 'male']
[https://opensanctions.org/entities/Q47536946]: 'Thandi Tobias' -> ['female', 'male']
[https://opensanctions.org/entities/Q50842679]: 'Abir Biswas' -> ['female', 'male']
[https://opensanctions.org/entities/Q5092257]: 'Cherrish Pryor' -> ['female', 'male']
[https://opensanctions.org/entities/Q5092774]: 'Cheryl Schonhardt-Bailey' -> ['female', 'male']
[https://opensanctions.org/entities/Q5099300]: 'Chimango Mughogho' -> ['female', 'male']
[https://opensanctions.org/entities/Q51105735]: 'Chen Xubin' -> ['female', 'male']
[https://opensanctions.org/entities/Q51265890]: 'Freddie Powell Sims' -> ['female', 'male']
[https://opensanctions.org/entities/Q5370301]: 'Eme Ufot Ekaette' -> ['female', 'male']
[https://opensanctions.org/entities/Q54806210]: 'Ljubow Iwanowna Gontscharenko' -> ['female', 'male']
[https://opensanctions.org/entities/Q54974716]: 'Ruzanna Arakelyan' -> ['female', 'male']
[https://opensanctions.org/entities/Q55614983]: 'Jeanne McNeill' -> ['female', 'male']
[https://opensanctions.org/entities/Q5591175]: 'Grace Folashade Bent' -> ['female', 'male']
[https://opensanctions.org/entities/Q56872154]: 'Eni Maulani Saragih' -> ['female', 'male']
[https://opensanctions.org/entities/Q58840728]: 'Tchimadem Hadattan Sanady' -> ['female', 'male']
[https://opensanctions.org/entities/Q60045011]: 'Natalya Vasilievna Kostenko' -> ['female', 'male']
[https://opensanctions.org/entities/Q61000617]: 'DUDA SALABERT ROSA' -> ['female', 'other']
[https://opensanctions.org/entities/Q61041277]: 'Matilde Siracusano' -> ['female', 'male']
[https://opensanctions.org/entities/Q6150518]: 'Jana Hunter' -> ['other', 'male']
[https://opensanctions.org/entities/Q61959890]: 'Kamal Krishna Das' -> ['female', 'male']
[https://opensanctions.org/entities/Q62713767]: 'Natalia Vladimirovna Kosykhina' -> ['female', 'male']
[https://opensanctions.org/entities/Q62714404]: 'Radionova Svetlana Gennadievna' -> ['female', 'male']
[https://opensanctions.org/entities/Q63065697]: 'Gulnara Shahinian' -> ['female', 'male']
[https://opensanctions.org/entities/Q6365478]: 'Kanti Singh' -> ['female', 'male']
[https://opensanctions.org/entities/Q64399316]: 'Lisa Nkosinathi Mangcu' -> ['female', 'male']
[https://opensanctions.org/entities/Q64399428]: 'Henry Andries Shembeni' -> ['female', 'male']
[https://opensanctions.org/entities/Q64734131]: 'Elvira Rinatovna Aitkulova' -> ['female', 'male']
[https://opensanctions.org/entities/Q64852980]: 'Akon Eyakenyi' -> ['female', 'male']
[https://opensanctions.org/entities/Q65575834]: 'Caroline Cussac' -> ['female', 'male']
[https://opensanctions.org/entities/Q65585475]: 'Yolande Houpert' -> ['female', 'male']
[https://opensanctions.org/entities/Q65603003]: 'Estelle Szabo' -> ['female', 'male']
[https://opensanctions.org/entities/Q65768417]: 'Anastasia Udaltsova' -> ['female', 'male']
[https://opensanctions.org/entities/Q66498828]: 'Hira Gurung' -> ['female', 'male']
[https://opensanctions.org/entities/Q67041767]: 'Ibrahima Soumah' -> ['female', 'male']
[https://opensanctions.org/entities/Q6951666]: 'Jothi, Shri N.' -> ['female', 'male']
[https://opensanctions.org/entities/Q73422]: 'Haniza Mohamed Talha' -> ['female', 'male']
[https://opensanctions.org/entities/Q83778801]: 'Adri Bom-Lemstra' -> ['female', 'male']
[https://opensanctions.org/entities/Q84607031]: 'Marianne Bernède' -> ['female', 'male']
[https://opensanctions.org/entities/Q85876999]: 'Robeyonce Lima' -> ['female', 'other']
[https://opensanctions.org/entities/Q869782]: 'Bouthaina Shaaban' -> ['female', 'male']
[https://opensanctions.org/entities/Q9132594]: 'Xiangqun Cui' -> ['female', 'male']
[https://opensanctions.org/entities/Q9135626]: 'Zhang Liping' -> ['female', 'male']
[https://opensanctions.org/entities/Q9176015]: 'Bogusława Towalewska' -> ['female', 'male']
[https://opensanctions.org/entities/Q96741326]: 'Nikkita Oliver' -> ['female', 'other']
[https://opensanctions.org/entities/Q97597769]: 'Cadí Seidi' -> ['female', 'male']
[https://opensanctions.org/entities/Q97660713]: 'Zikunova Irina Valerievna' -> ['female', 'male']
[https://opensanctions.org/entities/Q98233301]: 'Sylvie Farault' -> ['female', 'male']
[https://opensanctions.org/entities/Q98235741]: 'Sophie Pradel' -> ['female', 'male']
[https://opensanctions.org/entities/Q98247431]: 'Carole Cerveau' -> ['female', 'male']
[https://opensanctions.org/entities/Q98250576]: 'Laurence Le Guennic' -> ['female', 'male']
[https://opensanctions.org/entities/Q98258587]: 'Didier Robin' -> ['female', 'male']
[https://opensanctions.org/entities/Q99851996]: 'Clément Kuete Nymi Bemuna' -> ['female', 'male']
[https://opensanctions.org/entities/Q99926894]: 'Ardhedu Sahu' -> ['male', 'other']
```
