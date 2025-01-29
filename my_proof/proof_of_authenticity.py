from typing import List, Dict

def calculate_authenticity_score(contributions: List[Dict[str, any]], valid_domains: List[str]) -> float:
    """Calculate authenticity score by verifying contribution witnesses against valid domains."""
    valid_count = sum(
        1 for contribution in contributions
        if contribution.get('witnesses', '').endswith(tuple(valid_domains))
    )

    return valid_count / len(contributions) if contributions else 0
