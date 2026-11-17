"""全量元数据分析：7 事件 × N 区域 × 主题/人物/机构/情感/交叉提及"""
import pandas as pd, csv, sys, statistics, json
csv.field_size_limit(sys.maxsize)
from collections import Counter, defaultdict
from pathlib import Path

# 加载两个数据源
print("[Load] 5 events ...")
df5 = pd.read_csv('data/gdelt_events_v3/known_refined_url_pool.csv', low_memory=False)
print(f"  {len(df5)} rows")

print("[Load] 2 events ...")
df2 = pd.read_csv('../all_3_extra/data/gdelt_events/all_events_url_pool.csv', low_memory=False)
df2['url'] = df2['url'].astype(str).str.strip()
df2 = df2[df2['url'].str.startswith('http', na=False)]

# 给 df2 加 country_group_final (用简化规则)
from urllib.parse import urlparse
GENERIC_TLDS = {'com','org','net','edu','gov','mil','us','int','news','media','info','biz','pro','center','world','tv','fm','io','co','to','ws','nu','tk','cc','ai','sh','me','ly','so','st','ac'}
TLD_TO_REGION = {'uk':'Europe','de':'Europe','fr':'Europe','it':'Europe','es':'Europe','nl':'Europe','ie':'Europe','be':'Europe','at':'Europe','ch':'Europe','se':'Europe','no':'Europe','dk':'Europe','fi':'Europe','pl':'Europe','cz':'Europe','pt':'Europe','gr':'Europe','hu':'Europe','ro':'Europe','bg':'Europe','hr':'Europe','sk':'Europe','si':'Europe','lt':'Europe','lv':'Europe','ee':'Europe','lu':'Europe','mt':'Europe','cy':'Europe','is':'Europe','eu':'Europe','rs':'Europe','ba':'Europe','mk':'Europe','al':'Europe','md':'Europe','ru':'Russia','ua':'Ukraine','kz':'Russia','kg':'Russia','uz':'Russia','az':'Russia','am':'Russia','ge':'Russia','by':'Russia','cn':'China','jp':'EastAsia','kr':'EastAsia','sg':'EastAsia','hk':'EastAsia','tw':'EastAsia','mo':'EastAsia','mn':'EastAsia','kh':'EastAsia','la':'EastAsia','th':'EastAsia','vn':'EastAsia','ph':'EastAsia','my':'EastAsia','id':'EastAsia','bn':'EastAsia','tl':'EastAsia','mm':'EastAsia','in':'SouthAsia','pk':'SouthAsia','bd':'SouthAsia','lk':'SouthAsia','np':'SouthAsia','mv':'SouthAsia','bt':'SouthAsia','il':'Israel','ir':'Iran','sa':'MiddleEast','ae':'MiddleEast','qa':'MiddleEast','kw':'MiddleEast','bh':'MiddleEast','om':'MiddleEast','tr':'MiddleEast','eg':'MiddleEast','jo':'MiddleEast','lb':'MiddleEast','sy':'MiddleEast','iq':'MiddleEast','ye':'MiddleEast','ps':'MiddleEast','ly':'MiddleEast','dz':'MiddleEast','ma':'MiddleEast','tn':'MiddleEast','sd':'MiddleEast','so':'MiddleEast','mr':'MiddleEast','au':'EastAsia','nz':'EastAsia','za':'SouthAsia','ng':'SouthAsia','ke':'SouthAsia','et':'SouthAsia','tz':'SouthAsia','gh':'SouthAsia','ug':'SouthAsia','ca':'US','mx':'US','br':'US','ar':'US'}
DOMAIN_RULES = {'reuters.com':'Global','apnews.com':'Global','afp.com':'Global','cnn.com':'US','foxnews.com':'US','nytimes.com':'US','washingtonpost.com':'US','wsj.com':'US','npr.org':'US','bloomberg.com':'US','bbc.com':'Europe','bbc.co.uk':'Europe','theguardian.com':'Europe','dw.com':'Europe','france24.com':'Europe','lemonde.fr':'Europe','spiegel.de':'Europe','aljazeera.com':'MiddleEast','arabnews.com':'MiddleEast','thenationalnews.com':'MiddleEast','jpost.com':'Israel','haaretz.com':'Israel','timesofisrael.com':'Israel','ynetnews.com':'Israel','israelnationalnews.com':'Israel','presstv.ir':'Iran','tehrantimes.com':'Iran','tass.com':'Russia','rt.com':'Russia','sputniknews.com':'Russia','sputnikglobe.com':'Russia','chinadaily.com.cn':'China','globaltimes.cn':'China','xinhuanet.com':'China','people.com.cn':'China','scmp.com':'EastAsia','japantimes.co.jp':'EastAsia','koreaherald.com':'EastAsia','straitstimes.com':'EastAsia','indiatimes.com':'SouthAsia','thehindu.com':'SouthAsia','hindustantimes.com':'SouthAsia','dawn.com':'SouthAsia','tribune.com.pk':'SouthAsia','ndtv.com':'SouthAsia','firstpost.com':'SouthAsia','news18.com':'SouthAsia','republicworld.com':'SouthAsia','moneycontrol.com':'SouthAsia','thehindubusinessline.com':'SouthAsia','telegraphindia.com':'SouthAsia','india.com':'SouthAsia','prokerala.com':'SouthAsia','rediff.com':'SouthAsia'}

def norm(d):
    if pd.isna(d): return ''
    d = str(d).strip().lower()
    if d.startswith('http'):
        try: d = urlparse(d).netloc.lower()
        except: pass
    return d.replace('www.','').split('/')[0].split(':')[0]

def get_region(row):
    dn = str(row.get('domain_norm', row.get('domain', ''))).lower()
    dn = norm(dn)
    if dn in DOMAIN_RULES: return DOMAIN_RULES[dn]
    tld = dn.rsplit('.',1)[-1] if '.' in dn else ''
    if tld and tld not in GENERIC_TLDS and tld in TLD_TO_REGION: return TLD_TO_REGION[tld]
    if tld in GENERIC_TLDS: return 'US'
    cc = str(row.get('url_country_code','')).strip()
    if tld and tld in TLD_TO_REGION: return TLD_TO_REGION[tld]
    return 'Unknown'

# 过滤坏域名
import re as re_m
bad_kw = ['yahoo.','aol.','msn.','bing.','google.','youtube.','facebook.','twitter.',
    'instagram.','reddit.','tiktok.','iheart.','radio.','podcast','prnewswire.',
    'globenewswire.','businesswire.','marketscreener.','streetinsider.','seekingalpha.',
    'benzinga.','marketwatch.','investing.com','nasdaq.com','fool.com','bignewsnetwork.',
    'menafn.','miragenews.com','tickerreport.com','themarketsdaily.com','4-traders.com',
    'lelezard.com','pr-inside.com','onenewspage.com','hngn.com','itnewsonline.com',
    'econotimes.com','spacewar.com','digitaljournal.com','theusnews.com','naturalnews.com',
    'infowars.com','oann.com','russiaherald.com','heraldglobe.com','europesun.com',
    'middleeaststar.','arabherald.','flipboard.','newsbreak.','ground.news','accesswire.',
    'einpresswire.','newsfilecorp.','openpr.','einnews.']
df2['domain_norm'] = df2['domain'].apply(norm)
bad = pd.Series(False, index=df2.index)
for kw in bad_kw: bad |= df2['domain_norm'].str.contains(kw, na=False)
df2 = df2[~bad]
df2 = df2.drop_duplicates(subset=['event_id','url'])
df2['country_group_final'] = df2.apply(get_region, axis=1)
df2 = df2[df2['country_group_final'] != 'Unknown']
print(f"  {len(df2)} rows after clean")

# 合并
df = pd.concat([df5, df2], ignore_index=True)
print(f"\n  Total combined: {len(df)} rows")
print(f"  Events: {dict(df['event_id'].value_counts())}")

# ===== 分析 =====
EXCLUDE_THEMES = {'TAX_FNCACT','TAX_ETHNICITY','TAX_WORLDLANGUAGES','TAX_WORLDMAMMALS',
    'MEDIA_MSM','MEDIA_SOCIAL','SELF_IDENTIFIED_HUMAN_RIGHTS','USPEC_POLITICS_GENERAL1',
    'USPEC_POLICY1','GENERAL_GOVERNMENT','EPU_POLICY','EPU_POLICY_GOVERNMENT',
    'EPU_ECONOMY','EPU_ECONOMY_HISTORIC','LEADER','MANMADE_DISASTER_IMPLIED',
    'CRISISLEX_CRISISLEXREC','CRISISLEX_T03_DEAD','CRISISLEX_T02_INJURED',
    'CRISISLEX_T01_CAUTION_ADVICE','CRISISLEX_C','UNGP_FORESTS_RIVERS_OCEANS',
    'EDUCATION','SOC_POINTSOFINTEREST','SOC_GENERALCRIME',
    'GENERAL_HEALTH','MEDICAL','HEALTH_','TAX_DISEASE','TAX_FNCACT_',
    'ECON_','ETH_','MARITIME','NATURAL_DISASTER','SCIENCE','AGRICULTURE',
    'TOURISM','DEMOCRACY','ELECTION','LEGISLATION','IDEOLOGY','SECURITY_SERVICES',
    'MILITARY','ARMEDCONFLICT','BORDER','CLOSURE','DELAY','NEGOTIATIONS','REFUGEES',
    'DISPLACED','EVACUATION','MOVEMENT_GENERAL','PROTEST','ARREST','KILL','AFFECT',
    'WOUND','SEIZE','KIDNAP','TERROR','EXTREMISM','BULLYING','INFO_RUMOR',
    'EPU_CATS_','ENV_','FUELPRICES','SHORTAGE','POVERTY','UNREST_','TRIAL',
    'SLFID_','GOV_','INFO_','WB_','TAX_AIDGROUPS','TAX_POLITICAL_PARTY',
    'ROAD','RAIL','AVIATION','CYBER','HACKING','DATA','PRIVACY'}

results = {}
for eid in sorted(df['event_id'].unique()):
    sub = df[df['event_id'] == eid]
    countries = [c for c, n in sub['country_group_final'].value_counts().head(10).items() if n >= 100]
    
    event_result = {'total': len(sub), 'countries': {}}
    
    for country in countries:
        csub = sub[sub['country_group_final'] == country]
        cr = {'rows': len(csub)}
        
        # Themes
        tc = Counter()
        for val in csub['v2_locations'].dropna():
            for token in str(val).replace(';',',').split(','):
                token = token.strip().split('#')[0].strip()
                if 4 < len(token) < 60 and not token[0].isdigit():
                    if not any(token.startswith(s) for s in EXCLUDE_THEMES):
                        tc[token] += 1
        cr['themes'] = tc.most_common(12)
        
        # Persons
        pc = Counter()
        for val in csub['v2_persons'].dropna():
            for token in str(val).split(';'):
                token = token.strip().split(',')[0].strip()
                if 4 < len(token) < 40 and not token[0].isdigit():
                    pc[token] += 1
        cr['persons'] = pc.most_common(10)
        
        # Orgs
        oc = Counter()
        for val in csub['v2_organizations'].dropna():
            for token in str(val).split(';'):
                token = token.strip().split(',')[0].strip().lower()
                if 4 < len(token) < 50 and not token[0].isdigit() and token not in ('nan','none',''):
                    oc[token] += 1
        cr['orgs'] = oc.most_common(8)
        
        # Tone
        tones = []
        for val in csub['v2_tone'].dropna():
            try:
                parts = str(val).split(',')
                if len(parts) >= 2: tones.append(float(parts[0]))
            except: pass
        if tones:
            cr['tone_mean'] = round(statistics.mean(tones), 2)
            cr['tone_median'] = round(statistics.median(tones), 2)
        
        # Cross-mentions
        target_entities = {'United States':'US','U.S.':'US','America':'US','American':'US',
            'China':'China','Chinese':'China','Beijing':'China','Russia':'Russia',
            'Russian':'Russia','Moscow':'Russia','Israel':'Israel','Israeli':'Israel',
            'Iran':'Iran','Iranian':'Iran','Tehran':'Iran','Ukraine':'Ukraine',
            'Ukrainian':'Ukraine','Kyiv':'Ukraine','Kiev':'Ukraine',
            'Europe':'Europe','European':'Europe','EU':'Europe','United Kingdom':'Europe',
            'India':'SouthAsia','Japan':'EastAsia','Korea':'EastAsia','Australia':'EastAsia',
            'Pakistan':'SouthAsia','Brazil':'Global'}
        mc = Counter()
        for val in csub['v2_locations'].dropna():
            text = str(val).upper()
            for entity, label in target_entities.items():
                if entity.upper() in text: mc[label] += 1
        cr['mentions'] = mc.most_common(6)
        
        event_result['countries'][country] = cr
    
    results[eid] = event_result

# 输出
out_dir = Path('data/gdelt_events_v3/meta_analysis')
out_dir.mkdir(parents=True, exist_ok=True)

for eid, er in results.items():
    print(f'\n{"="*80}')
    print(f'  {eid}  ({er["total"]:,} rows)')
    print(f'{"="*80}')
    
    # Tone gradient
    print('\n  TONE GRADIENT (most negative → least negative):')
    tone_ranking = sorted([(c, cr.get('tone_mean', 0)) for c, cr in er['countries'].items()], key=lambda x: x[1])
    for c, t in tone_ranking:
        bar = '█' * int(abs(t)*4)
        print(f'  {c:15s} {t:+6.2f}  {bar}')
    
    # Themes per country
    print('\n  TOP THEMES PER COUNTRY:')
    for c in sorted(er['countries']):
        cr = er['countries'][c]
        themes_str = ', '.join('{}({:,})'.format(t, n) for t, n in cr['themes'][:6])
        print(f'  {c:15s} ({cr["rows"]:>6,} rows) | {themes_str}')
    
    # Persons
    print('\n  TOP PERSONS PER COUNTRY:')
    for c in sorted(er['countries']):
        cr = er['countries'][c]
        pers_str = ', '.join('{}({:,})'.format(t, n) for t, n in cr['persons'][:5])
        print(f'  {c:15s} | {pers_str}')
    
    # Cross-mentions
    print('\n  WHO MENTIONS WHOM:')
    for c in sorted(er['countries']):
        cr = er['countries'][c]
        ment_str = ', '.join('{}({:,})'.format(e, n) for e, n in cr['mentions'])
        print(f'  {c:15s} -> {ment_str}')
    
    print()

# Save JSON
with open(out_dir / 'all_events_meta.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f'\nResults saved to {out_dir / "all_events_meta.json"}')
