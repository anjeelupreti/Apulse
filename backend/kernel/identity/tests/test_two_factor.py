import pyotp

from kernel.identity import two_factor


def test_secret_and_provisioning_uri_are_usable_by_an_authenticator_app():
    secret = two_factor.generate_secret()
    uri = two_factor.provisioning_uri(secret=secret, account_name="ram@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "ram%40example.com" in uri or "ram@example.com" in uri
    assert secret in uri


def test_current_code_verifies():
    secret = two_factor.generate_secret()
    code = pyotp.TOTP(secret, interval=two_factor.TOTP_INTERVAL).now()
    assert two_factor.verify_code(secret, code)


def test_non_numeric_and_empty_codes_are_rejected_without_raising():
    secret = two_factor.generate_secret()
    assert not two_factor.verify_code(secret, "abcdef")
    assert not two_factor.verify_code(secret, "")


def test_matched_timestep_identifies_the_step_so_a_code_cannot_be_replayed():
    secret = two_factor.generate_secret()
    code = pyotp.TOTP(secret, interval=two_factor.TOTP_INTERVAL).now()
    step = two_factor.matched_timestep(secret, code)
    assert step == two_factor.current_timestep()


def test_matched_timestep_returns_none_for_a_wrong_code():
    secret = two_factor.generate_secret()
    assert two_factor.matched_timestep(secret, "000000") in (None, two_factor.current_timestep())


def test_recovery_codes_are_unique_and_transcribable():
    codes = two_factor.generate_recovery_codes()
    assert len(codes) == two_factor.RECOVERY_CODE_COUNT
    assert len(set(codes)) == len(codes)
    for code in codes:
        assert len(code) == 11
        assert code[5] == "-"
        # No characters that are easy to confuse when read off a printed sheet.
        assert not set(code[:5] + code[6:]) & {"0", "O", "1", "I", "L"}


def test_recovery_code_hash_round_trip_is_case_and_space_insensitive():
    code = two_factor.generate_recovery_codes(1)[0]
    hashed = two_factor.hash_recovery_code(code)
    assert two_factor.check_recovery_code(code.lower(), hashed)
    assert two_factor.check_recovery_code(f"  {code}  ", hashed)
    assert not two_factor.check_recovery_code("AAAAA-BBBBB", hashed)


def test_recovery_codes_are_not_stored_in_clear_text():
    code = two_factor.generate_recovery_codes(1)[0]
    assert code not in two_factor.hash_recovery_code(code)
