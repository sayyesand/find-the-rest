import numpy as np
from app.audio_fingerprint import fingerprint_samples, audio_fingerprint_similarity

def mixture(freqs, seconds=8, sr=8000, gain=1.0):
    t=np.arange(int(seconds*sr),dtype=np.float32)/sr
    x=sum((1/(i+1))*np.sin(2*np.pi*f*t) for i,f in enumerate(freqs))
    return (gain*x).astype(np.float32)

def score(a,b):
    fa=fingerprint_samples(a)
    fb=fingerprint_samples(b)
    return audio_fingerprint_similarity(fa,fb)[0]

def test_audio_fingerprint_is_volume_invariant():
    a=mixture([220,440,880],gain=.2)
    b=mixture([220,440,880],gain=.9)
    assert score(a,b) > .90

def test_audio_fingerprint_tolerates_small_codec_like_noise():
    rng=np.random.default_rng(4)
    a=mixture([261.6,523.25,1046.5])
    b=a + rng.normal(0,.008,size=a.shape).astype(np.float32)
    assert score(a,b) > .82

def test_audio_fingerprint_rejects_different_spectral_content():
    a=mixture([180,360,720])
    b=mixture([1250,1900,2700])
    assert score(a,b) < .90

def test_silence_has_no_fingerprint():
    fp=fingerprint_samples(np.zeros(16000,dtype=np.float32))
    assert fp.windows == 0
    assert fp.hashes == ()
