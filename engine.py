"""Transparent, offline similarity and AI-writing *signal* screening.
No method in this module establishes plagiarism or AI authorship as a fact.
"""
from collections import Counter
from difflib import SequenceMatcher
import html
import math
import re

SENTENCE_RE = re.compile(r'(?<=[.!?])\s+(?=["\'“‘(]*[A-Z0-9])|\n{2,}')
WORD_RE = re.compile(r"\b[\w]+(?:['’-][\w]+)*\b", re.UNICODE)
STOP = set('a an the and or but is are was were to of in for on with by it this that these those as at from be been being not can we they he she you i our your their its than then'.split())
GENERIC = ['in today\'s rapidly evolving', 'it is important to note', 'in conclusion', 'plays a crucial role', 'in the modern world', 'a wide range of', 'furthermore', 'moreover', 'delve into', 'landscape', 'seamlessly', 'it is worth noting', 'in summary', 'in the realm of', 'this highlights the importance']


def words(text):
    return WORD_RE.findall(text or '')


def sentences(text):
    text = (text or '').strip()
    if not text:
        return []
    chunks = [s.strip() for s in SENTENCE_RE.split(text) if s.strip()]
    result = []
    for c in chunks:
        # Handle paragraphs without terminal punctuation while preserving source text.
        result.append(c)
    return result


def tokens(text):
    return [w.lower() for w in words(text) if len(w) > 2 and w.lower() not in STOP]


def cosine(a, b):
    ca, cb = Counter(tokens(a)), Counter(tokens(b))
    if not ca or not cb:
        return 0.0
    dot = sum(v * cb.get(k, 0) for k, v in ca.items())
    den = math.sqrt(sum(v*v for v in ca.values()) * sum(v*v for v in cb.values()))
    return dot / den if den else 0.0


def similarity(a, b):
    """Combined token cosine and sequence overlap; inspect candidate matches manually."""
    lexical = cosine(a, b)
    sequence = SequenceMatcher(None, ' '.join(a.lower().split()), ' '.join(b.lower().split()), autojunk=False).ratio()
    return round(0.65 * lexical + 0.35 * sequence, 4)


def plagiarism_analysis(text, references, threshold=0.58):
    ss = sentences(text)
    all_source_sentences = [(name, sent) for name, body in references.items() for sent in sentences(body) if len(words(sent)) >= 5]
    flagged = []
    word_count = len(words(text))
    covered = 0
    for i, sent in enumerate(ss):
        best = (0, '', '')
        if len(words(sent)) >= 5:
            for name, ref_sent in all_source_sentences:
                score = similarity(sent, ref_sent)
                if score > best[0]:
                    best = (score, name, ref_sent)
        score, name, match = best
        hit = score >= threshold
        if hit:
            covered += len(words(sent))
        flagged.append({'index': i+1, 'text': sent, 'score': round(score*100, 1), 'source': name if hit else '', 'match': match if hit else '', 'flagged': hit})
    return {'word_count': word_count, 'sentence_count': len(ss), 'flagged_count': sum(s['flagged'] for s in flagged),
            'similarity_percent': round(covered / word_count * 100, 1) if word_count else 0.0,
            'matched_sources': len(set(s['source'] for s in flagged if s['source'])), 'sentences': flagged,
            'references_count': len(references), 'threshold': threshold}


def ai_signals(text):
    """Explainable style features, NOT a validated AI detector or authorship probability."""
    ss = sentences(text)
    results = []
    covered = 0
    for i, sent in enumerate(ss):
        reasons = []
        low = sent.lower()
        sw = words(sent)
        if any(phrase in low for phrase in GENERIC):
            reasons.append('Contains a common formulaic or generic academic phrase')
        if len(sw) >= 23:
            reasons.append('Long, highly structured sentence')
        if len(sw) >= 10 and len(set(w.lower() for w in sw)) / len(sw) < 0.7:
            reasons.append('Repeated vocabulary within the sentence')
        if sum(1 for w in sw if w.lower().endswith(('tion','ment','ity','ance'))) >= 4:
            reasons.append('High density of abstract academic nouns')
        if low.startswith(('furthermore', 'moreover', 'additionally', 'in conclusion', 'in summary')):
            reasons.append('Predictable transition or summary opening')
        flagged = len(reasons) >= 2 or any(phrase in low for phrase in GENERIC)
        if flagged:
            covered += len(sw)
        results.append({'index': i+1, 'text': sent, 'flagged': flagged, 'reasons': reasons,
                        'signal_count': len(reasons)})
    wc = len(words(text))
    return {'word_count': wc, 'sentence_count': len(ss), 'flagged_count': sum(x['flagged'] for x in results),
            'signal_coverage_percent': round(100 * covered/wc, 1) if wc else 0.0,
            'unflagged_percent': round(100*(wc-covered)/wc,1) if wc else 0.0,
            'sentences': results}


def highlighted_html(items, kind='plagiarism'):
    out = []
    for s in items:
        content = html.escape(s['text'])
        if s['flagged']:
            typ = 'match' if kind == 'plagiarism' else 'ai'
            desc = f"Similarity {s.get('score', 0)}%" if kind == 'plagiarism' else 'Stylistic signal — review recommended'
            out.append(f'<span class="mark {typ}" title="{html.escape(desc)}">{content}</span>')
        else:
            out.append(f'<span class="unmarked">{content}</span>')
    return ' '.join(out) if out else '<span class="muted">No text to display.</span>'
