from contextlib import contextmanager
import httpx
import pytest
from whylab.security import TrustedRetriever


@pytest.mark.parametrize('statuses,expected_calls,succeeds',[
    ([502,200],2,True),([503,200],2,True),([504,200],2,True),
    ([400,200],1,False),([503,503],2,False),
])
def test_only_transient_http_failures_get_one_bounded_retry(monkeypatch,statuses,expected_calls,succeeds):
    calls=[]
    @contextmanager
    def stream(client,method,url,**kwargs):
        calls.append(kwargs)
        request=httpx.Request(method,url)
        response=httpx.Response(statuses[len(calls)-1],content=b'actual upstream bytes',request=request)
        try: yield response
        finally: response.close()
    monkeypatch.setattr(httpx.Client,'stream',stream)
    monkeypatch.setattr('whylab.security.time.sleep',lambda seconds:None)
    retriever=TrustedRetriever(['irsa.ipac.caltech.edu'],timeout=10)
    if succeeds:
        assert retriever.get('https://irsa.ipac.caltech.edu/SIA') == b'actual upstream bytes'
    else:
        with pytest.raises(httpx.HTTPStatusError):retriever.get('https://irsa.ipac.caltech.edu/SIA')
    assert len(calls)==expected_calls
    assert all(0<call['timeout']<=10 for call in calls)
    assert retriever.client().follow_redirects is False
    retriever.close()
