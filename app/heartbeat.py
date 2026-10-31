"""Theo dõi cửa sổ app còn mở hay không (giao diện gửi tín hiệu mỗi 20 giây)."""
import time

_last = [time.time()]


def beat():
    _last[0] = time.time()


def last_seen() -> float:
    return _last[0]
