"""Conservative French intake patterns for facts explicitly written by the client.

No risk score, target, sector or investment allocation is invented. Hypothetical
quiz amounts are kept separate from the client's actual capital and loss limit.
"""
from __future__ import annotations

import re
import unicodedata

_WORDS = dict(enumerate(('zero un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize').split()))
_WORDS.update({17:'dix-sept',18:'dix-huit',19:'dix-neuf'})
for tens, stem in ((20,'vingt'),(30,'trente'),(40,'quarante'),(50,'cinquante'),(60,'soixante')):
    for unit in range(10):
        _WORDS[tens+unit] = stem if not unit else stem + ('-et-un' if unit == 1 else '-' + _WORDS[unit])
for n in range(70,80):
    _WORDS[n] = 'soixante-' + ('et-' if n == 71 else '') + _WORDS[n-60]
for n in range(80,100):
    _WORDS[n] = 'quatre-vingts' if n == 80 else 'quatre-vingt-' + _WORDS[n-80]
_FR_NUMBERS = {word: str(n) for n, word in _WORDS.items()}
_FR_NUMBERS['une'] = '1'
_WORD_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(w).replace(r'\-', r'[- ]') for w in sorted(_FR_NUMBERS, key=len, reverse=True))
                           + r')(?=\s+(?:(?:prochaines?|prochains?)\s+)?(?:ans?\b|annees?\b|mois\b|mille\b|millions?\b|dollars?\b|pour\s+cent\b))', re.I)


def numeric_text(text: str) -> str:
    """French grouped amounts/decimal commas and contextual number words; preserve other text."""
    text = unicodedata.normalize('NFC', text)
    text = re.sub(r'(?<=\d)[ \u00a0\u202f](?=\d{3}(?:\D|$))', '', text)
    text = re.sub(r'(?<=\d),(?=\d{1,2}(?!\d))', '.', text)
    # Match folded text, but only replace matched number words in the original.
    folded = ''.join(c for c in unicodedata.normalize('NFD', text) if not unicodedata.combining(c))
    matches = list(_WORD_PATTERN.finditer(folded))
    for match in reversed(matches):
        word = re.sub(r'[ -]+', '-', match[0].lower())
        text = text[:match.start()] + _FR_NUMBERS[word] + text[match.end():]
    return text


def folded(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', numeric_text(text)) if not unicodedata.combining(c)).lower().replace('’', "'")


def parse(text: str) -> dict:
    t = folded(text)
    p = {}
    if not re.search(r"\b(?:je|j'ai|j'investis|mon|mes|retraite|epargne|portefeuille)\b", t):
        return p
    def number(field, pattern):
        match = re.search(pattern, t)
        if match:
            p[field] = float(match[1].replace(',', ''))
    name = re.search(r"\b(?:je m['’]appelle|mon nom est)\s+([\wÀ-ÿ-]+)", text, re.I)
    if name:
        p['name'] = name[1]
    number('age', r"\bj'ai\s+(\d{1,3})\s+ans\b")
    number('horizon_years', r"(?:\bsur\s+|\bhorizon\s+(?:de\s+)?|\bretraite\s+dans\s+)(\d+(?:\.\d+)?)\s+ans\b")
    amount = r'(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?:\$|dollars?|cad)'
    number('capital', r"(?:j'ai|capital\s+(?:de|est\s+de))\s+" + amount + r'(?:\s+a\s+investir|\s+(?:a\s+)?placer|\s+(?:d.epargne|epargnes?))')
    number('monthly_contribution', amount + r'\s*(?:par|chaque)\s+mois\b')
    number('emergency_fund_months', r"(?:fonds\s+d'urgence|coussin\s+(?:de\s+securite|d'urgence))[^.!?\n]{0,60}?(\d+(?:\.\d+)?)\s+mois\b")
    number('years_experience', r"(?:j'investis\s+depuis\s+|)(\d+(?:\.\d+)?)\s+ans\s+d'experience\b")
    number('years_experience', r"j'investis\s+depuis\s+(\d+(?:\.\d+)?)\s+ans\b")
    number('max_loss_pct', r'(?:baisse|perte|recul)\s+(?:maximale?|maximum)[^.!?\n%]{0,70}?(\d+(?:\.\d+)?)\s*%')
    if 'max_loss_pct' not in p:
        number('max_loss_pct', r"(?:ne\s+(?:veux|peux|souhaite)\s+pas|n'accepte\s+pas\s+de)\s+perdre\s+plus\s+de\s+(\d+(?:\.\d+)?)\s*%")
    for value, pattern in [('uncertain',r'revenu[^.!?\n]{0,25}(?:incertain|instable)'),('variable',r'revenu[^.!?\n]{0,25}(?:variable|irregulier)'),('stable',r'revenu[^.!?\n]{0,25}\bstable\b')]:
        if re.search(pattern,t):
            p['income_stability'] = value
            break
    for value, pattern in [('growth',r'faire\s+fructifier|croissance\s+(?:de\s+mon|du)\s+(?:capital|portefeuille)|croissance\s+a\s+long\s+terme'),('retirement',r'preparer\s+(?:ma|la)\s+retraite|(?:ma\s+)?retraite\s+dans'),('income',r'(?:obtenir|generer)\s+(?:un\s+)?revenu\s+regulier')]:
        if re.search(pattern,t):
            p['objective'] = value
            break
    for value, pattern in [('buy_more',r"j'investirais\s+(?:davantage|plus)|j'acheterais\s+(?:davantage|plus)|acheter\s+davantage"),('sell_all',r'je\s+vendrais\s+tout'),('sell_some',r'je\s+vendrais\s+une\s+partie'),('hold',r'je\s+(?:garderais|conserverais)\s+(?:mes|les)\s+placements|je\s+ne\s+vendrais\s+pas|je\s+ne\s+ferais\s+rien')]:
        if re.search(pattern,t):
            p['loss_reaction'] = value
            break
    for value, pattern in [('intermediate',r'connaissances[^.!?\n]{0,30}\bintermediaires?\b'),('basic',r'connaissances[^.!?\n]{0,30}\b(?:de\s+base|basiques?)\b'),('advanced',r'connaissances[^.!?\n]{0,30}\bavancees?\b'),('none',r'je\s+debute|aucune\s+experience')]:
        if re.search(pattern,t):
            p['knowledge_level'] = value
            break
    if re.search(r"(?:aucun\s+retrait|pas\s+(?:besoin\s+de\s+)?retir|pas\s+de\s+retrait)",t):
        p['withdrawal_share_3y'] = 0.0
    if re.search(r'portefeuille\s+de\s+marche', t):
        p['investment_mode'] = 'market'
    # Preferences must be expressed as interests, separately from the quiz stories.
    interest = re.search(r"(?:je\s+m'interesse|mes\s+interets)[^.!?\n]*",t)
    if interest:
        p['interests'] = [key for key, pat in [('ai',r'intelligence\s+artificielle|\bia\b'),('crypto',r'crypto|bitcoin'),('tech',r'technolog'),('esg',r'\besg\b|responsable'),('dividends',r'dividende'),('canada',r'canad'),('us',r'etats.unis|americain'),('gold',r"\bl'or\b"),('bonds',r'obligation')] if re.search(pat,interest[0])]
    held = re.search(r"j'ai\s+(?:deja\s+)?(?:detenu|possede|achete)[^.!?\n]*",t)
    if held:
        p['products_held'] = [key for key, pat in [('stocks',r'actions?'),('etfs',r'\bfnb\b|\betf\b'),('crypto',r'crypto'),('bonds',r'obligations?'),('gics',r'\bcpg\b'),('funds',r'fonds\s+communs')] if re.search(pat,held[0])]
    exclusions = [key for key, pat in [('crypto',r'crypto|bitcoin'),('fossil_fuels',r'fossil|petrole|gaz'),('single_stocks',r'actions?\s+individuelles?')] if re.search(r"(?:eviter|exclure|pas\s+de)\s+(?:les?\s+|d[eu]\s+)?(?:"+pat+r')',t)]
    if exclusions:
        p['exclusions'] = exclusions
    # Only explicit desired amounts/requests; avoid the hypothetical quiz capital.
    number('target_amount', r"(?:je\s+(?:vise|souhaite\s+atteindre)|objectif\s+(?:de|est\s+de))\s+"+amount)
    req = re.search(r"(?:je\s+(?:veux|souhaite|voudrais)|j'aimerais)[^.!?\n]{0,30}?(\d+(?:\.\d+)?)\s*%\s+(?:dans|en)\s+([\w.-]+)",t)
    if req:
        from .extractor import ticker_of
        p['requested_positions'] = {ticker_of(req[2]):float(req[1])/100}
    number('ev_answer_pct', r'(?:ma\s+reponse[^.!?\n]{0,90}?rendement\s+moyen|rendement\s+moyen[^.!?\n]{0,30}?(?:est|:))\s*(?:est\s*)?(\d+(?:\.\d+)?)\s*%')
    from .. import kyc
    bets = {}
    starts = [m.start() for m in re.finditer(r"\bsur\s+(?:10000|100000)\s*(?:\$|dollars?)", t)]
    stories = [t[start:end] for start, end in zip(starts, [*starts[1:], len(t)])]
    for line in stories:
        if not re.search(r'garanti|minimal|minimum', line):
            continue
        for bet in kyc.BETS:
            up, down = int(bet.up*100), abs(int(bet.down*100))
            if bet.id == 'bet_savings':
                match_story = '120000' in line and '95000' in line
            else:
                match_story = bool(re.search(rf'gagner\s+{up}\s*%',line) and re.search(rf'perdre\s+{down}\s*%',line))
            if not match_story:
                continue
            answer = re.search(r'(?:est|minimum)\s+(\d+(?:\.\d+)?)\s*%',line)
            if answer:
                bets[bet.id] = float(answer[1])/100
            elif bet.id == 'bet_savings':
                answer = re.search(r'(?:minimum|accepterais)\s+(\d+)\s*(?:\$|dollars)',line)
                if answer:
                    bets[bet.id] = round(float(answer[1])/bet.amount-1,6)
    if bets:
        p['kyc_bets'] = bets
    return p
