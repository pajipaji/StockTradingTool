import pytest

pytestmark = pytest.mark.network


def test_real_snapshot_builds():
    from backend.core.net import force_ipv4
    force_ipv4()
    from backend.fetchers.a_index import fetch_a_index
    out = fetch_a_index()
    assert out["indices"], "应至少返回一个指数"
