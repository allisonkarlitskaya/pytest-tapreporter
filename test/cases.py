import pytest


class Common:
    def test_pass(self) -> None:
        pass

    def test_pass_output(self) -> None:
        print("Hello world")

    def test_fail(self) -> None:
        pytest.fail()

    def test_fail_output(self) -> None:
        print("Hello world")
        pytest.fail()

    def test_fail_reason(self) -> None:
        pytest.fail("broken")

    def test_fail_reason_output(self) -> None:
        print("Hello world")
        pytest.fail("broken")

    def test_raises(self) -> None:
        assert False

    def test_raises_output(self) -> None:
        print("Hello world")
        assert False

    def test_skip(self) -> None:
        pytest.skip()

    def test_skip_output(self) -> None:
        print("Hello world")
        pytest.skip()

    def test_skip_reason(self) -> None:
        pytest.skip("not supported")

    def test_skip_reason_output(self) -> None:
        print("Hello world")
        pytest.skip("not supported")


class TestNormal(Common):
    pass


@pytest.mark.xfail
class TestXfail(Common):
    pass


@pytest.mark.xfail(strict=True)
class TestXfailStrict(Common):
    pass


@pytest.mark.xfail(reason="needs work")
class TestXfailReason(Common):
    pass


@pytest.mark.xfail(reason="needs work", strict=True)
class TestXfailReasonStrict(Common):
    pass


@pytest.mark.skip
class TestSkip(Common):
    pass


@pytest.mark.skipif(True, reason="not supported")
class TestSkipConditional(Common):
    pass


@pytest.mark.skip(reason="not supported")
class TestSkipReason(Common):
    pass
