#!/usr/bin/env bash
# Office items peploop's discovery cannot reach, made reachable by one to five
# additive statements each.
#
# Every item below is a real office that carries no P31, no P17/P1001, or no
# link to the body it heads, so neither the descent nor the usage query finds
# it. Each was read live on 2026-10-04 and only the statements it lacks are
# here. Additive only: no removal, no rank change, and no P2388, which this
# workbench never writes. Where the right value was not clear, the case is in
# research/position_items.md §10o and not here.
#
#   bash scripts/body_fixes.sh            # print the commands, write nothing
#   bash scripts/body_fixes.sh --apply    # run them
#
# Several lines on one item share the revision that was read. Wikibase
# accepts a stale --baserevid when every edit since it is the same user's, so
# the batch goes through in order; an edit by anyone else in between makes
# the next line fail with an edit conflict, which is the point of carrying it.
set -euo pipefail

if [[ "${1:-}" != "--apply" ]]; then
  grep -E '^(# |wb )' "$0" | sed -n '/^# ---/,$p'
  echo
  echo "dry: nothing written. Re-run with --apply to make these edits." >&2
  exit 0
fi

# --- Q106040759 'Chief of Defence Staff' (read at rev 1556686751)
# Chief of Defence Staff -> P279 chief of defence (Q5097014)
wb add-claim Q106040759 P279 Q5097014 --baserevid 1556686751 --maxlag 5 --summary "office data fix: P279 chief of defence, as its Jamaican sibling Q85751928 and 28 of 40 typed armed-forces chiefs"
# Chief of Defence Staff -> P17 Trinidad and Tobago (Q754)
wb add-claim Q106040759 P17 Q754 --baserevid 1556686751 --maxlag 5 --summary "office data fix: P17 Trinidad and Tobago, the state whose defence force it heads (enwiki: professional head of the TTDF)"
# Chief of Defence Staff -> P1001 Trinidad and Tobago (Q754)
wb add-claim Q106040759 P1001 Q754 --baserevid 1556686751 --maxlag 5 --summary "office data fix: P1001 Trinidad and Tobago, national office: P1001 = P17"
# Chief of Defence Staff -> P2389 Trinidad and Tobago Defence Force (Q761495)
wb add-claim Q106040759 P2389 Q761495 --baserevid 1556686751 --maxlag 5 --summary "office data fix: P2389 Trinidad and Tobago Defence Force, the body it heads"

# --- Q85751924 'Chief Secretary of Tobago' (read at rev 2467017640)
# Chief Secretary of Tobago -> P31 position (Q4164871)
wb add-claim Q85751924 P31 Q4164871 --baserevid 2467017640 --maxlag 5 --summary "office data fix: P31 position, an office with no type"
# Chief Secretary of Tobago -> P17 Trinidad and Tobago (Q754)
wb add-claim Q85751924 P17 Q754 --baserevid 2467017640 --maxlag 5 --summary "office data fix: P17 Trinidad and Tobago, sub-national office: P17 the state"
# Chief Secretary of Tobago -> P1001 Tobago (Q185111)
wb add-claim Q85751924 P1001 Q185111 --baserevid 2467017640 --maxlag 5 --summary "office data fix: P1001 Tobago, sub-national office: P1001 the polity governed"
# Chief Secretary of Tobago -> P361 Tobago House of Assembly (Q7811539)
wb add-claim Q85751924 P361 Q7811539 --baserevid 2467017640 --maxlag 5 --summary "office data fix: P361 Tobago House of Assembly, seat in the Tobago House of Assembly"

# --- Q85794414 'Presiding Officer of the Tobago House of Assembly' (read at rev 1357860804)
# Presiding Officer of the Tobago House of Assembly -> P31 position (Q4164871)
wb add-claim Q85794414 P31 Q4164871 --baserevid 1357860804 --maxlag 5 --summary "office data fix: P31 position, an office with no type"
# Presiding Officer of the Tobago House of Assembly -> P279 speaker (Q1758037)
wb add-claim Q85794414 P279 Q1758037 --baserevid 1357860804 --maxlag 5 --summary "office data fix: P279 speaker, presiding officer of the assembly, as 152 sub-national speaker items"
# Presiding Officer of the Tobago House of Assembly -> P17 Trinidad and Tobago (Q754)
wb add-claim Q85794414 P17 Q754 --baserevid 1357860804 --maxlag 5 --summary "office data fix: P17 Trinidad and Tobago, sub-national office: P17 the state"
# Presiding Officer of the Tobago House of Assembly -> P1001 Tobago (Q185111)
wb add-claim Q85794414 P1001 Q185111 --baserevid 1357860804 --maxlag 5 --summary "office data fix: P1001 Tobago, sub-national office: P1001 the polity governed"
# Presiding Officer of the Tobago House of Assembly -> P2389 Tobago House of Assembly (Q7811539)
wb add-claim Q85794414 P2389 Q7811539 --baserevid 1357860804 --maxlag 5 --summary "office data fix: P2389 Tobago House of Assembly, the assembly it presides over"

# --- Q123054908 "gouverneur de la Banque de la république d'Haïti" (read at rev 2101863520)
# gouverneur de la Banque de la république d'Haïti -> P31 public office (Q294414)
wb add-claim Q123054908 P31 Q294414 --baserevid 2101863520 --maxlag 5 --summary "office data fix: P31 public office, an office with no type; four of four central-bank governor siblings measured use public office"
# gouverneur de la Banque de la république d'Haïti -> P279 central bank governor (Q107363151)
wb add-claim Q123054908 P279 Q107363151 --baserevid 2101863520 --maxlag 5 --summary "office data fix: P279 central bank governor, as its four sibling governors (CU, CO, BY, JM)"
# gouverneur de la Banque de la république d'Haïti -> P17 Haiti (Q790)
wb add-claim Q123054908 P17 Q790 --baserevid 2101863520 --maxlag 5 --summary "office data fix: P17 Haiti, national office"
# gouverneur de la Banque de la république d'Haïti -> P1001 Haiti (Q790)
wb add-claim Q123054908 P1001 Q790 --baserevid 2101863520 --maxlag 5 --summary "office data fix: P1001 Haiti, national office: P1001 = P17"
# gouverneur de la Banque de la république d'Haïti -> P2389 Bank of the Republic of Haiti (Q2883379)
wb add-claim Q123054908 P2389 Q2883379 --baserevid 2101863520 --maxlag 5 --summary "office data fix: P2389 Bank of the Republic of Haiti, the bank it heads"

# --- Q132736192 'Conseiller-Président au sein du Conseil Présidentiel de Transition' (read at rev 2316496135)
# Conseiller-Président au sein du Conseil Présidentiel de Transition -> P31 position (Q4164871)
wb add-claim Q132736192 P31 Q4164871 --baserevid 2316496135 --maxlag 5 --summary "office data fix: P31 position, an office with no type"
# Conseiller-Président au sein du Conseil Présidentiel de Transition -> P17 Haiti (Q790)
wb add-claim Q132736192 P17 Q790 --baserevid 2316496135 --maxlag 5 --summary "office data fix: P17 Haiti, national office"
# Conseiller-Président au sein du Conseil Présidentiel de Transition -> P1001 Haiti (Q790)
wb add-claim Q132736192 P1001 Q790 --baserevid 2316496135 --maxlag 5 --summary "office data fix: P1001 Haiti, national office: P1001 = P17"
# Conseiller-Président au sein du Conseil Présidentiel de Transition -> P361 Transitional Presidential Council (Q124846311)
wb add-claim Q132736192 P361 Q124846311 --baserevid 2316496135 --maxlag 5 --summary "office data fix: P361 Transitional Presidential Council, seat in the collegial body (collegial-organ seats name it under P361)"

# --- Q119848570 'Comandante General del Ejército de la República Dominicana' (read at rev 2318754601)
# Comandante General del Ejército de la República Dominicana -> P31 position (Q4164871)
wb add-claim Q119848570 P31 Q4164871 --baserevid 2318754601 --maxlag 5 --summary "office data fix: P31 position, an office with no type (92 of 93 armed-forces chiefs measured)"
# Comandante General del Ejército de la República Dominicana -> P17 Dominican Republic (Q786)
wb add-claim Q119848570 P17 Q786 --baserevid 2318754601 --maxlag 5 --summary "office data fix: P17 Dominican Republic, national office"
# Comandante General del Ejército de la República Dominicana -> P1001 Dominican Republic (Q786)
wb add-claim Q119848570 P1001 Q786 --baserevid 2318754601 --maxlag 5 --summary "office data fix: P1001 Dominican Republic, national office: P1001 = P17"

# --- Q135659026 'Начальнік Службы бяспекі Прэзідэнта Рэспублікі Беларусь' (read at rev 2388996959)
# Начальнік Службы бяспекі Прэзідэнта Рэспублікі Беларусь -> P17 Belarus (Q184)
wb add-claim Q135659026 P17 Q184 --baserevid 2388996959 --maxlag 5 --summary "office data fix: P17 Belarus, national office"
# Начальнік Службы бяспекі Прэзідэнта Рэспублікі Беларусь -> P1001 Belarus (Q184)
wb add-claim Q135659026 P1001 Q184 --baserevid 2388996959 --maxlag 5 --summary "office data fix: P1001 Belarus, national office: P1001 = P17"

# --- Q85751928 'Chief of Defence Staff' (read at rev 1589421205)
# Chief of Defence Staff -> P1001 Jamaica (Q766)
wb add-claim Q85751928 P1001 Q766 --baserevid 1589421205 --maxlag 5 --summary "office data fix: P1001 Jamaica, national office: P1001 = P17"
