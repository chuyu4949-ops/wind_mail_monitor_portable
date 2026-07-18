from __future__ import annotations


SUBJECT_KEYWORD_PLACEHOLDERS = {"塔号", "邮箱主题关键词"}


def active_subject_keywords(values: object) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    return [
        str(item).strip()
        for item in values
        if str(item).strip() and str(item).strip() not in SUBJECT_KEYWORD_PLACEHOLDERS
    ]


def subject_matches_keywords(subject: str, values: object) -> bool:
    subject_lower = subject.lower()
    return any(keyword.lower() in subject_lower for keyword in active_subject_keywords(values))
