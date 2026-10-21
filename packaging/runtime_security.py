"""PyInstaller hook: apply cache protection before any application import."""
from core.security.diskcache_guard import guard_diskcache

guard_diskcache()
