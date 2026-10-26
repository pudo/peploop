---
description: Handoff for sending the China zh.wikipedia sample batches (10 offices, 52 people) for the Mass-editing review
date: 2026-10-23
tags: [peploop, china, sample, send]
---

# China zh sample send — handoff

## Brief

1. Two zh.wikipedia sample batches for the Mass-editing review are ready and **unsent**: 10 new offices (Appendix A), then 52 people, 122 statement lines (Appendix B).
2. Offices: `mint --country cn --submit --id 58111 --id 58109 --id 60154 --id 61291 --id 63321 --id 60965 --id 58481 --id 60642 --id 58013 --id 58217`. Batch #135 never reached QS3 (Toolforge outage, 22–23 Oct); its recover has run for 9 rows, and #63321 is still `creating`, which the next submit's recover settles.
3. People, after the offices land: `send --country cn` plus the `--qid` flags below, then `--submit`. The dry run gives create 102, switch 14, merge 2, termed 4, and 4 rows already on Wikidata; the lines are in `data/peploop/send/cn_sample_people.qs`.
4. Since the posted review page, the only change in the people batch is Sun Jianguo's added 2018–2023 NPC term. It comes from `be9816f` (an open term closes at the next one; a multi-term statement gets dates), and the reviewer flagged that row.
5. Afterwards: audit both batches, fill the diff links into `User:Pudox/PEP/zh-sample` (draft: `data/zh_sample_review.wiki`), and reply in the thread. The full China tranches and the verifier note for 91 inferred-end terms are still open decisions.

## Appendix A — the 10 offices

| id | Office | zh label | Kind | Holders |
| --- | --- | --- | --- | --- |
| 58111 | Governor of Zhejiang | 浙江省人民政府省长 | governor | 12 |
| 58109 | Governor of Hunan | 湖南省人民政府省长 | governor | 10 |
| 60154 | Chairman of the Standing Committee of the Guangdong People's Congress | 广东省人民代表大会常务委员会主任 | congress chair | 8 |
| 61291 | Chairman of the Jiangsu Committee of the CPPCC | 中国人民政治协商会议江苏省委员会主席 | CPPCC chair | 5 |
| 63321 | President of the Sichuan High People's Court | 四川省高级人民法院院长 | high court president | 6 |
| 60965 | Chief Procurator of Tianjin People's Procuratorate | 天津市人民检察院检察长 | chief procurator | 5 |
| 58481 | Party Secretary of Ningbo | 中国共产党宁波市委员会书记 | city Party secretary | 12 |
| 60642 | Communist Party Secretary of Changsha | 中国共产党长沙市委员会书记 | city Party secretary | 9 |
| 58013 | Mayor of Xi'an | 西安市市长 | mayor | 9 |
| 58217 | Director of the State Administration of Foreign Exchange | 国家外汇管理局局长 | national agency head | 6 |

Known oddities, accepted for the sample:

- The two Party secretaries carry P279 Q988456 and a P2389 committee, but no P1001.
- #58217 has a generic description and no P17.
- #60965 uses P31 Q294414, where the others use Q4164871.

## Appendix B — the 52 people

Seed 20261019, drawn from people whose accepted rows all cite zh.wikipedia. Roles are the planned P39 rows; the other rows are P569, P570, P21 or P27.

| QID | Name | Stratum | Roles (P39) | Rows |
| --- | --- | --- | --- | --- |
| [Q104722387](https://www.wikidata.org/wiki/Q104722387) | 孙建国 | current | National People's Congress deputy 2018–2023; National People's Congress deputy 2023 | 3 |
| [Q105717831](https://www.wikidata.org/wiki/Q105717831) | 曹小林 | current | ambassador of China to Tonga 2020-01–2023-12; Chinese Ambassador to Qatar 2024-01 | 5 |
| [Q110405868](https://www.wikidata.org/wiki/Q110405868) | 蓝虎 | current | ambassador of China to Venezuela 2023-04 | 4 |
| [Q110406056](https://www.wikidata.org/wiki/Q110406056) | Guo Wei (diplomat) 郭伟 | current | Chinese representative to Palestine (Q120146893, unlabelled) 2018-04–2023-03; Chinese Ambassador to Jordan 2025-11 | 4 |
| [Q111693526](https://www.wikidata.org/wiki/Q111693526) | 蒋薇 | current | Chinese Ambassador to Antigua and Barbuda 2025-11 | 4 |
| [Q114690383](https://www.wikidata.org/wiki/Q114690383) | 马珊珊 | current | mayor of Shenyang 2026-09-29 | 3 |
| [Q117746210](https://www.wikidata.org/wiki/Q117746210) | Li Changguan 李常官 | current | Minister of Civil Affairs of the People's Republic of China 2026-08-28 | 3 |
| [Q120696965](https://www.wikidata.org/wiki/Q120696965) | 吴伟 | current | Chinese Ambassador to the Federated States of Micronesia 2023-06 | 4 |
| [Q125473715](https://www.wikidata.org/wiki/Q125473715) | 张斌 | current | Ambassador of the People's Republic of China to Angola 2024-02 | 3 |
| [Q127427764](https://www.wikidata.org/wiki/Q127427764) | 陈志清 | current | National People's Congress deputy 2023 | 3 |
| [Q127428030](https://www.wikidata.org/wiki/Q127428030) | 严家蓉 | current | ambassador of China to the Bahamas 2024-07 | 3 |
| [Q127428051](https://www.wikidata.org/wiki/Q127428051) | 杨晓光 | current | ambassador of China to Papua New Guinea 2024-07 | 4 |
| [Q134507222](https://www.wikidata.org/wiki/Q134507222) | Jing Puqiu 景普秋 | current | member of the National Committee of the Chinese People's Political Consultative Conference 2023 | 1 |
| [Q135645077](https://www.wikidata.org/wiki/Q135645077) | 张洋 | current | ambassador of the People's Republic of China to Cape Verde 2025-07 | 4 |
| [Q137878572](https://www.wikidata.org/wiki/Q137878572) | 蒋小燕 | current | Chinese Ambassador to the Republic of Macedonia 2025-10 | 4 |
| [Q15900499](https://www.wikidata.org/wiki/Q15900499) | Jing Hanchao 景汉朝 | current | Member of the Standing Committee of the National People's Congress 2023-03 | 1 |
| [Q16077835](https://www.wikidata.org/wiki/Q16077835) | Cheng Lin 程林 | current | Member of the Standing Committee of the National People's Congress 2023-03 | 2 |
| [Q24833565](https://www.wikidata.org/wiki/Q24833565) | Zhong Denghua 钟登华 | current | member of the National Committee of the Chinese People's Political Consultative Conference 2023-03 | 2 |
| [Q30944216](https://www.wikidata.org/wiki/Q30944216) | Luo Dongchuan 罗东川 | current | Secretary of the CPC Qinghai Committee 2026-09-22 | 1 |
| [Q47674422](https://www.wikidata.org/wiki/Q47674422) | 张柱 | current | Minister of Agriculture and Rural Affairs 2026-04-30 | 3 |
| [Q78116691](https://www.wikidata.org/wiki/Q78116691) | 金李 | current | member of the National Committee of the Chinese People's Political Consultative Conference 2023 | 1 |
| [Q8038979](https://www.wikidata.org/wiki/Q8038979) | Wu Weishan 吳為山 | current | standing member of the National Committee of the Chinese People's Political Consultative Conference 2023-03-10 | 1 |
| [Q8461965](https://www.wikidata.org/wiki/Q8461965) | Wang Jun 王军 (1958年) | current | member of the National Committee of the Chinese People's Political Consultative Conference 2023-01-17 | 1 |
| [Q85358954](https://www.wikidata.org/wiki/Q85358954) | 余劲松 | current | Chinese Ambassador to Seychelles 2016-12–2018-09; Chinese Ambassador to Morocco 2025-09 | 4 |
| [Q104722586](https://www.wikidata.org/wiki/Q104722586) | 张毅 | died | — | 3 |
| [Q11067525](https://www.wikidata.org/wiki/Q11067525) | 张穹 | died | — | 1 |
| [Q8248847](https://www.wikidata.org/wiki/Q8248847) | Li Suwen (died 2022) 李素文 | died | — | 1 |
| [Q9447554](https://www.wikidata.org/wiki/Q9447554) | Gao Jianmin 高建民 | died | — | 2 |
| [Q117746707](https://www.wikidata.org/wiki/Q117746707) | 马海军 | details | — | 1 |
| [Q117746785](https://www.wikidata.org/wiki/Q117746785) | 张利文 | details | — | 2 |
| [Q117747017](https://www.wikidata.org/wiki/Q117747017) | 曹阿民 | details | — | 2 |
| [Q117747129](https://www.wikidata.org/wiki/Q117747129) | 尹晓东 | details | — | 2 |
| [Q47672818](https://www.wikidata.org/wiki/Q47672818) | 李长友 | details | — | 1 |
| [Q9349754](https://www.wikidata.org/wiki/Q9349754) | Che Xiulan 车秀兰 | details | — | 1 |
| [Q104381961](https://www.wikidata.org/wiki/Q104381961) | Guo Puxiao 郭普校 | former | National People's Congress deputy 2026-06-26 | 1 |
| [Q105717963](https://www.wikidata.org/wiki/Q105717963) | 柴文睿 | former | Ambassadors of China to Mongolia 2020-01–2023-09 | 4 |
| [Q10871569](https://www.wikidata.org/wiki/Q10871569) | Yan Xiaomin 严小敏 | former | ambassador of the People's Republic of China to Equatorial Guinea 2007–2010 | 1 |
| [Q11096090](https://www.wikidata.org/wiki/Q11096090) | 李宝钧 | former | Ambassador of the People's Republic of China to Guinea-Bissau 2010-11–2013-07 | 4 |
| [Q116226591](https://www.wikidata.org/wiki/Q116226591) | 王擎 | former | Chinese Ambassador to Sierra Leone 2023-01–2025-11 | 4 |
| [Q16924855](https://www.wikidata.org/wiki/Q16924855) | 罗小光 | former | ambassador of China to Sudan 2011-09–2014-10 | 2 |
| [Q198026](https://www.wikidata.org/wiki/Q198026) | Zhou Xiaochuan 周小川 | former | member of the Central Committee of the Chinese Communist Party 2002-11–2012-11 | 1 |
| [Q20687922](https://www.wikidata.org/wiki/Q20687922) | Wang Guoping 王国平 | former | Party Secretary of Hangzhou 2000-04–2010-01 | 1 |
| [Q30942633](https://www.wikidata.org/wiki/Q30942633) | 金红军 | former | Ambassador of the People's Republic of China to Guinea-Bissau 2017-04–2020-08 | 3 |
| [Q360563](https://www.wikidata.org/wiki/Q360563) | Wu Bangguo 吴邦国 | former | member of the Politburo of the Chinese Communist Party 1992-10-19–2012-11-15 | 1 |
| [Q50419574](https://www.wikidata.org/wiki/Q50419574) | Chen Guoping 程国平 | former | Chinese Ambassador to Kazakhstan 2008-09–2010-02; Assistant Minister of Foreign Affairs of the People's Republic of China 2010-02–2011-09; Vice-minister of Foreign Affairs of the People's Republic of China 2011-09–2015-11 | 3 |
| [Q67935307](https://www.wikidata.org/wiki/Q67935307) | 李昌林 | former | Chinese Ambassador to Morocco 2021-04–2025-07 | 3 |
| [Q702616](https://www.wikidata.org/wiki/Q702616) | Chen Jianguo 陈建国 | former | Secretary of the CPC Ningxia Committee 2002-03–2010-07 | 1 |
| [Q78122906](https://www.wikidata.org/wiki/Q78122906) | Xia Xinmin 夏心旻 | former | mayor of Nanjing 2022-04-11–2023-01-08 | 2 |
| [Q7929640](https://www.wikidata.org/wiki/Q7929640) | Wang Guangya 王光亚 | former | Vice-minister of Foreign Affairs of the People's Republic of China 2008-09-26–2010-10-08; Member of the Standing Committee of the National People's Congress 2018-03-18–2023-03 | 2 |
| [Q8045173](https://www.wikidata.org/wiki/Q8045173) | Xu Zongheng 许宗衡 | former | National People's Congress deputy 2009-08-27 | 2 |
| [Q8463267](https://www.wikidata.org/wiki/Q8463267) | Zhang Weiqing 张维庆 | former | Director of the National Family Planning Commission 2003-03–2008-03; standing member of the National Committee of the Chinese People's Political Consultative Conference 2008-03–2013-03 | 2 |
| [Q9075888](https://www.wikidata.org/wiki/Q9075888) | Yang Zhengwu 杨正午 | former | Member of the Standing Committee of the National People's Congress 2008-03–2013-03 | 1 |

Send flags:

```
--qid Q104381961 --qid Q104722387 --qid Q104722586 --qid Q105717831 --qid Q105717963 --qid Q10871569 --qid Q110405868 --qid Q110406056 --qid Q11067525 --qid Q11096090 --qid Q111693526 --qid Q114690383 --qid Q116226591 --qid Q117746210 --qid Q117746707 --qid Q117746785 --qid Q117747017 --qid Q117747129 --qid Q120696965 --qid Q125473715 --qid Q127427764 --qid Q127428030 --qid Q127428051 --qid Q134507222 --qid Q135645077 --qid Q137878572 --qid Q15900499 --qid Q16077835 --qid Q16924855 --qid Q198026 --qid Q20687922 --qid Q24833565 --qid Q30942633 --qid Q30944216 --qid Q360563 --qid Q47672818 --qid Q47674422 --qid Q50419574 --qid Q67935307 --qid Q702616 --qid Q78116691 --qid Q78122906 --qid Q7929640 --qid Q8038979 --qid Q8045173 --qid Q8248847 --qid Q8461965 --qid Q8463267 --qid Q85358954 --qid Q9075888 --qid Q9349754 --qid Q9447554
```
