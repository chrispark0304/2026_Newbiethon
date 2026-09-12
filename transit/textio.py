"""인코딩 방어용 텍스트 읽기.

서울 열린데이터광장·공공데이터포털 CSV는 대부분 **CP949**로 내려온다.
fetch.py가 받을 때 UTF-8로 정규화하지만, 누가 손으로 받아 넣을 수도 있으므로
읽는 쪽에서도 양쪽을 모두 받아 준다.
"""
from __future__ import annotations
from pathlib import Path

#: 시도 순서. 앞쪽이 성공하면 거기서 멈춘다.
ENCODINGS = ("utf-8-sig", "cp949")


def read_text(path: Path, encodings=ENCODINGS) -> str:
    blob = Path(path).read_bytes()
    for enc in encodings:
        try:
            return blob.decode(enc)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(
        "unknown", blob, 0, 1,
        f"{path} 를 {encodings} 중 어느 것으로도 읽지 못했습니다.")


def to_utf8(blob: bytes, encodings=ENCODINGS) -> str:
    """다운로드 직후 바이트를 UTF-8 문자열로 정규화한다."""
    for enc in encodings:
        try:
            return blob.decode(enc)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", blob, 0, 1, "인코딩 판별 실패")
