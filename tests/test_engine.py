from engine import plagiarism_analysis, ai_signals, similarity, words, highlighted_html

def test_exact_reference():
    x='Natural language processing helps computers interpret human language in many applications.'
    r=plagiarism_analysis(x,{'paper':x})
    assert r['similarity_percent']==100.0
    assert r['flagged_count']==1
    assert r['matched_sources']==1

def test_no_reference_match():
    x='Photosynthesis provides energy for the majority of green plants on earth.'
    r=plagiarism_analysis(x,{'unrelated':'Economic inequality affects access to universities around the world.'})
    assert r['flagged_count']==0

def test_empty_text():
    assert plagiarism_analysis('',{})['sentence_count']==0
    assert ai_signals('')['signal_coverage_percent']==0

def test_ai_signal_not_probability():
    r=ai_signals("In today's rapidly evolving landscape, it is important to note that communication plays a crucial role.")
    assert r['flagged_count']==1
    assert 'signal_coverage_percent' in r
    assert 'ai_probability' not in r

def test_html_escaped():
    text='<script>alert(1)</script> Plagiarism detection requires careful academic review.'
    res=plagiarism_analysis(text,{})
    rendered=highlighted_html(res['sentences'])
    assert '<script>' not in rendered
    assert '&lt;script&gt;' in rendered

def test_similarity_symmetry():
    a='Research papers often cite prior findings from other authors.'
    b='Authors cite findings in academic research papers.'
    assert abs(similarity(a,b)-similarity(b,a))<1e-10


def test_word_count():
    assert len(words('One two, three.'))==3
