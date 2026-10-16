import io
import json
import pytest
from scripts.audit_setup_model_sources import audit


@pytest.mark.parametrize('change', [None, 'hash', 'size', 'license', 'missing_file', 'revision'])
def test_pinned_metadata_must_match_every_field(change):
    entry = {'source_repo':'synthetic/model', 'filename':'test.gguf',
             'url':'https://huggingface.co/synthetic/model/resolve/abc/test.gguf',
             'sha256':'a'*64, 'approx_bytes':123, 'license':'Apache-2.0'}
    data = {'sha':'abc', 'cardData':{'license':'apache-2.0'},'siblings':[
        {'rfilename':'test.gguf','lfs':{'sha256':'a'*64,'size':123}}]}
    if change == 'revision':data['sha']='other'
    if change == 'hash':data['siblings'][0]['lfs']['sha256']='b'*64
    if change == 'size':data['siblings'][0]['lfs']['size']=124
    if change == 'license':data['cardData']['license']='other'
    if change == 'missing_file':data['siblings']=[]
    def opener(url, **kwargs):
        assert url.endswith('/revision/abc?blobs=true')
        return io.BytesIO(json.dumps(data).encode())
    assert audit({'test':entry},opener=opener)['ok'] is (change is None)


def test_empty_catalog_is_not_successful_verification():
    assert not audit({})['ok']
