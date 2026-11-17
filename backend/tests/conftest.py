"""
백엔드 테스트 공통 설정 (2026-11-17, 전체 검토 6번)

실행: cd backend && venv/bin/python -m pytest
- 네트워크·Firestore·LLM을 부르지 않는다. 필요한 곳은 가짜(FakeDB, 가짜 스크래퍼·LLM)로 바꾼다.
- 이번 검토에서 실제로 고장 났던 지점(판정 규칙, 요약 검사, 헬스체크 판정, 새올 목록 파싱,
  본문 추출, 파이프라인 실행 기록)을 고정해 다시 깨지면 바로 알게 하는 것이 목적이다.
"""

import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# 테스트에서 실수로 Gemini를 부르지 않게 기본값을 ollama로 (호출 자체는 각 테스트에서 가짜로 바꿈)
os.environ.setdefault("LLM_PROVIDER", "ollama")


class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _Doc:
    def __init__(self, store, key):
        self.store, self.key = store, key

    def set(self, data):
        self.store[self.key] = dict(data)

    def get(self):
        return _Snap(self.store.get(self.key))


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def limit(self, n):
        return _Query(self.rows[:n])

    def get(self):
        return [_Snap(r) for r in self.rows]


class _Collection:
    def __init__(self):
        self.docs = {}

    def add(self, data):
        self.docs[f"auto{len(self.docs)}"] = dict(data)

    def document(self, key):
        return _Doc(self.docs, key)

    def order_by(self, field, direction=None):
        return _Query(sorted(self.docs.values(), key=lambda r: r[field], reverse=True))


class FakeDB:
    """monitoring·scraping_function이 쓰는 만큼만 흉내 낸 메모리 Firestore."""

    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, _Collection())
