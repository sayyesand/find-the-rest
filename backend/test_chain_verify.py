from app.chain_verify import LinkEvidence, chain_confidence

def test_chain_confidence_penalizes_weakest_link():
    strong = LinkEvidence(.8,.7,.75,.7,.76,True)
    weak = LinkEvidence(.3,.2,.25,.35,.29,False)
    score = chain_confidence([strong, weak])
    assert score < 0.55

def test_chain_confidence_high_when_all_links_strong():
    a = LinkEvidence(.8,.6,.75,.7,.73,True)
    b = LinkEvidence(.72,.58,.7,.68,.69,True)
    score = chain_confidence([a,b])
    assert score > 0.65
