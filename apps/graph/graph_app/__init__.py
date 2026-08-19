"""Grafová apka pro viewBase3 — první apka postavená proti kontraktu.

Leží ZÁMĚRNĚ mimo balíček `viewbase`: kdyby byla uvnitř, nedokázali bychom,
že hranice mezi workbenchem a apkou je skutečná a ne jen nakreslená.
"""
from .backend import ContentRefused, GraphApp
from .model import Change, GraphContent

__all__ = ["GraphApp", "GraphContent", "Change", "ContentRefused"]
