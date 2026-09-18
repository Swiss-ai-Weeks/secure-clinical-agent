"""Patient360 backend: the policy spine (Build Plan §4, §5).

Every read passes one PDP; every PDP call writes one audit row; identity comes
from the session cookie or the run token, never from a prompt or a tool argument.
"""
