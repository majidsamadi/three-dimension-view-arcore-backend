"""Dev integration suite for the four 3D services (wave 3 plan §6.5.3, D9).

Stdlib only.  Runs from ``.github/workflows/dev-integration.yml`` (manual dispatch on
``main``) against the public dev endpoints with synthetic data (Q07 first slice).  It
holds no AWS credentials: identities come from Cognito's public SRP + TOTP sign-in for
two owner-provided synthetic accounts.  Locally it only runs against stubs
(``tests/test_dev_integration.py``).  It never prints or stores tokens or secrets.
"""
