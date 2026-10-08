"""TOTP codes computed locally from an Item's seed (same formats rbw accepts).

Expected values come from RFC 6238 Appendix B and RFC 4226 Appendix D.
"""

import pytest

from qutewarden.totp import totp_code

# RFC 6238 test seeds (ASCII "1234567890" repeated), base32-encoded.
SHA1_SEED = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
SHA256_SEED = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZA===="
SHA512_SEED = ("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
               "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNA=")


@pytest.mark.parametrize("now, code", [(59, "94287082"), (1111111109, "07081804"),
                                       (2000000000, "69279037")])
def test_otpauth_sha1_eight_digits_matches_rfc6238(now, code):
    uri = f"otpauth://totp/Example:alice?secret={SHA1_SEED}&digits=8"
    assert totp_code(uri, now=now) == code


def test_otpauth_sha256_and_sha512_match_rfc6238():
    assert totp_code(f"otpauth://totp/x?secret={SHA256_SEED}&algorithm=SHA256&digits=8",
                     now=59) == "46119246"
    assert totp_code(f"otpauth://totp/x?secret={SHA512_SEED}&algorithm=SHA512&digits=8",
                     now=59) == "90693936"


def test_otpauth_defaults_to_six_digits_sha1_thirty_seconds():
    assert totp_code(f"otpauth://totp/x?secret={SHA1_SEED}", now=59) == "287082"


def test_otpauth_custom_period():
    # period 60 at t=119 is counter 1, same as the 30 s vector at t=59.
    assert totp_code(f"otpauth://totp/x?secret={SHA1_SEED}&period=60", now=119) == "287082"


@pytest.mark.parametrize(
    "seed", [SHA1_SEED, SHA1_SEED.lower(), " GEZD GNBV GY3T QOJQ GEZD GNBV GY3T QOJQ "])
def test_bare_base32_seed_any_case_or_spacing(seed):
    assert totp_code(seed, now=59) == "287082"


def test_steam_seed_gives_five_char_steam_code():
    # RFC 4226 Appendix D: counter 1 truncates to 1094287082; Steam encodes it in base 26.
    assert totp_code(f"steam://{SHA1_SEED}", now=59) == "PV9M4"


@pytest.mark.parametrize("seed", ["not base32 !!", "otpauth://hotp/x?secret=GEZDGNBV",
                                  "otpauth://totp/x", "https://example.com"])
def test_invalid_seed_raises_value_error(seed):
    with pytest.raises(ValueError):
        totp_code(seed, now=59)


def test_now_defaults_to_current_time():
    assert len(totp_code(SHA1_SEED)) == 6
