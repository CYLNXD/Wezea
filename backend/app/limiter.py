"""
Module partagé — instance SlowAPI unique pour tout le projet.
Importé par main.py et les routers qui ont besoin du rate limiting.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
