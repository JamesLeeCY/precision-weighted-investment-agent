"""前瞻規格 fv5：前 500 名、與 fv3 共用快照、規則函式與 fv3 相同（只差股票池大小）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forward import run_forward_fv3 as fv3  # noqa: E402
from forward import run_forward_fv5 as fv5  # noqa: E402


def test_fv5_differs_from_fv3_only_in_universe_size():
    assert fv5.TOP_N == 500 and fv3.TOP_N == 300
    assert fv5.snapshot("2026-10-13").cache_dir == fv3.snapshot("2026-10-13").cache_dir
    assert fv5.PREDICTIONS.parent.name == "fv5"
    h3, h5 = fv3.source_hashes(), fv5.source_hashes()
    for k in ("score_members", "shortable_flags", "tranche_weights", "segment_return", "member_frame"):
        assert h3[f"fv3.{k}"] == h5[f"fv5.{k}"]                 # 規則程式碼相同
    assert h3["fv3.constants"] != h5["fv5.constants"]            # 只有常數（TOP_N）不同
