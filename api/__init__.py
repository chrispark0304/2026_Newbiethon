"""같이살집 백엔드.

`.env`를 여기서 먼저 읽는다. api/kakao.py 같은 모듈이 임포트 시점에 환경변수를
읽으므로, 하위 모듈보다 반드시 앞서야 한다.
"""
from . import env as _env

LOADED_ENV_FILES = _env.load()
