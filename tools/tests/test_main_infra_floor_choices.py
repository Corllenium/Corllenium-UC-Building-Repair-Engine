"""Every fresh MAIN INFRA floor can be named on the candidate and review command lines."""
import re
from pathlib import Path

from tools.main_infra_progress import FLOORS


def test_candidate_and_review_accept_all_seven_fresh_floors():
    import tools.main_infra_candidate as candidate
    import tools.main_infra_review as review
    assert tuple(candidate.FLOOR_CHOICES) == tuple(review.FLOOR_CHOICES) == FLOORS == ('1F', '2F', '3F', '4F', '5F', '6F', '7F')
    for module in (candidate, review):
        source = Path(module.__file__).read_text(encoding='utf-8')
        assert re.search(r"add_argument\('--floor', choices=list\(FLOOR_CHOICES\)", source), module.__file__
        assert "choices=['1F', '4F']" not in source
